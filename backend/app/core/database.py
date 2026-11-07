"""
Lapisan database WASKITA (SQLAlchemy 2.0 async).

Mendukung dua backend:
- SQLite via ``sqlite+aiosqlite:///./data/waskita.db`` (default, tanpa server).
  Folder induk file database dibuat otomatis. Pool memakai ``NullPool``
  (file) atau ``StaticPool`` (``:memory:``) sehingga aman dipakai dari
  beberapa event loop (tes, skrip ``asyncio.run``), dan opsi ``pool_size``
  tidak dipakai karena tidak berlaku untuk SQLite.
- PostgreSQL via ``postgresql+asyncpg://user:pass@host:5432/waskita``.
  URL ``postgres://`` / ``postgresql://`` otomatis diubah ke driver asyncpg.

Kontrak (docs/CONTRACTS.md §1): ``engine``, ``AsyncSessionLocal``, ``Base``,
``get_db()``, ``init_db()``.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from app.core.config import settings

logger = logging.getLogger(__name__)


def normalize_database_url(raw_url: str) -> URL:
    """Ubah URL database menjadi URL dengan driver async yang didukung."""
    url = make_url(raw_url)
    backend = url.get_backend_name()
    if backend in ("postgres", "postgresql") and url.drivername in ("postgres", "postgresql", "postgresql+psycopg2"):
        url = url.set(drivername="postgresql+asyncpg")
    elif backend == "sqlite" and url.drivername == "sqlite":
        url = url.set(drivername="sqlite+aiosqlite")
    return url


def is_sqlite_url(url: URL) -> bool:
    return url.get_backend_name() == "sqlite"


def _ensure_sqlite_dir(url: URL) -> None:
    database = url.database
    if not database or database == ":memory:" or database.startswith("file:"):
        return
    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _build_engine(raw_url: str) -> AsyncEngine:
    url = normalize_database_url(raw_url)
    kwargs: dict[str, Any] = {"echo": settings.debug}

    if is_sqlite_url(url):
        _ensure_sqlite_dir(url)
        in_memory = not url.database or url.database == ":memory:"
        kwargs["poolclass"] = StaticPool if in_memory else NullPool
        kwargs["connect_args"] = {"timeout": 30}
    else:
        kwargs.update(
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
        )

    eng = create_async_engine(url, **kwargs)

    if is_sqlite_url(url):

        @event.listens_for(eng.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record) -> None:  # pragma: no cover - dipanggil driver
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return eng


engine: AsyncEngine = _build_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Basis deklaratif untuk semua model di ``app.models``."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """
    Dependency FastAPI: satu sesi per request.

    Endpoint yang menulis data sebaiknya memanggil ``await db.commit()``
    sendiri sebelum mengembalikan respons; commit di sini hanya jaring
    pengaman untuk perubahan yang tertinggal.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.in_transaction():
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Buat semua tabel yang belum ada (create_all). Dipanggil di lifespan."""
    import app.models  # noqa: F401  (mendaftarkan semua model ke Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    logger.info("Database siap (%s)", engine.url.render_as_string(hide_password=True))


def _literal_default(column) -> Any:
    """Nilai default skalar kolom (untuk ALTER TABLE), atau None."""
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    return default.arg


def _add_missing_columns(sync_conn) -> None:
    """
    Migrasi ADITIF ringan: tambahkan kolom baru (yang ada di model tetapi belum
    ada di tabel lama) dengan ``ALTER TABLE … ADD COLUMN``. Tidak pernah
    menghapus/mengubah kolom. Untuk perubahan skema yang lebih besar pakai
    alat migrasi (Alembic).
    """
    from sqlalchemy import inspect as sa_inspect

    insp = sa_inspect(sync_conn)
    existing_tables = set(insp.get_table_names())
    preparer = sync_conn.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            col_type = col.type.compile(dialect=sync_conn.dialect)
            ddl = f"ALTER TABLE {preparer.quote(table.name)} ADD COLUMN {preparer.quote(col.name)} {col_type}"
            value = _literal_default(col)
            if value is not None and not callable(value):
                if isinstance(value, bool):
                    lit = ("1" if value else "0") if sync_conn.dialect.name == "sqlite" else ("TRUE" if value else "FALSE")
                elif isinstance(value, (int, float)):
                    lit = repr(value)
                else:
                    lit = "'" + str(value).replace("'", "''") + "'"
                ddl += f" DEFAULT {lit}"
                if not col.nullable:
                    ddl += " NOT NULL"
            sync_conn.exec_driver_sql(ddl)
            logger.warning("Migrasi aditif: kolom %s.%s ditambahkan.", table.name, col.name)


async def dispose_db() -> None:
    await engine.dispose()
