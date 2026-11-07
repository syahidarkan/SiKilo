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
    logger.info("Database siap (%s)", engine.url.render_as_string(hide_password=True))


async def dispose_db() -> None:
    await engine.dispose()
