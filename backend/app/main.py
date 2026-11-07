"""
Aplikasi FastAPI WASKITA — agen AI pengatur energi UMKM + PLTS atap tepat ukuran.
"""
from __future__ import annotations

import importlib
import inspect
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from typing import Optional

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import endpoints_auth, endpoints_devices
from app.core.auth import bootstrap_admin, get_secret_key
from app.core.config import settings
from app.core.database import AsyncSessionLocal, dispose_db, init_db

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
logger = logging.getLogger("waskita")

API_PREFIX = "/api/v1"

# Router fitur dimuat dinamis: modul yang belum ada dilewati, modul yang
# gagal di-import dicatat (dan menggagalkan start di production).
_FEATURE_ROUTERS: tuple[tuple[str, str], ...] = (
    ("app.api.v1.endpoints_telemetry", API_PREFIX),
    ("app.api.v1.endpoints_dispatch", API_PREFIX),
    ("app.api.v1.endpoints_sizing", API_PREFIX),
    ("app.api.v1.endpoints_agent", API_PREFIX),
    ("app.api.v1.endpoints_dashboard", API_PREFIX),
    ("app.api.v1.endpoints_umkm", API_PREFIX),
    ("app.api.v1.endpoints_public", API_PREFIX),
    ("app.api.v1.endpoints_ws", ""),
)

router_status: dict[str, str] = {}


def _import_optional(module_name: str) -> Optional[ModuleType]:
    """Import modul; ``None`` bila modul itu sendiri tidak ada."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            return None
        raise


def _include_feature_routers(application: FastAPI) -> None:
    for module_name, prefix in _FEATURE_ROUTERS:
        short = module_name.rsplit(".", 1)[-1]
        try:
            module = _import_optional(module_name)
        except Exception as exc:  # noqa: BLE001
            if settings.is_production:
                raise
            logger.exception("Router %s gagal dimuat; endpoint-nya tidak tersedia.", short)
            router_status[short] = f"gagal: {type(exc).__name__}"
            continue
        if module is None:
            router_status[short] = "tidak ada"
            continue
        router = getattr(module, "router", None)
        if not isinstance(router, APIRouter):
            router_status[short] = "tidak ada router"
            logger.warning("Modul %s tidak punya atribut `router`.", module_name)
            continue
        application.include_router(router, prefix=prefix)
        router_status[short] = "ok"


async def _maybe_await(value) -> None:
    if inspect.isawaitable(value):
        await value


def _preload_models() -> None:
    try:
        from app.digital_twin.solar_engine import get_solar_engine

        get_solar_engine()
    except Exception:  # noqa: BLE001
        logger.exception("Gagal memuat solar engine saat startup.")

    try:
        ppo = _import_optional("app.agent.ppo_scheduler")
    except Exception:  # noqa: BLE001
        logger.exception("Gagal meng-import app.agent.ppo_scheduler.")
        ppo = None
    loader = getattr(ppo, "get_ppo_scheduler", None) if ppo else None
    if callable(loader):
        try:
            loader()
        except Exception:  # noqa: BLE001
            logger.exception("Gagal memuat agen PPO saat startup (penjadwal lain tetap tersedia).")


def _scheduler_module() -> Optional[ModuleType]:
    try:
        return _import_optional("app.services.scheduler")
    except Exception:  # noqa: BLE001
        logger.exception("Gagal meng-import app.services.scheduler; penjadwal tidak dijalankan.")
        return None


@asynccontextmanager
async def lifespan(application: FastAPI):
    get_secret_key()  # gagal cepat bila SECRET_KEY kosong di production
    await init_db()
    async with AsyncSessionLocal() as db:
        await bootstrap_admin(db)

    if settings.preload_models:
        _preload_models()

    scheduler = _scheduler_module()
    if scheduler is not None and hasattr(scheduler, "start_scheduler"):
        await _maybe_await(scheduler.start_scheduler())

    try:
        yield
    finally:
        if scheduler is not None and hasattr(scheduler, "shutdown_scheduler"):
            try:
                await _maybe_await(scheduler.shutdown_scheduler())
            except Exception:  # noqa: BLE001
                logger.exception("Gagal menghentikan penjadwal.")
        await dispose_db()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API WASKITA — agen AI pengatur energi UMKM dan perencana PLTS atap "
        "tepat ukuran. Mencakup pemantauan beban (NILM), tiruan digital, penjadwal "
        "mesin hemat biaya, sizing PLTS (Permen ESDM No. 2/2024), dan rapor kelayakan "
        "untuk pembiayaan hijau."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

_origins = [o.strip() for o in settings.cors_origins if o and o.strip()]
_allow_all = "*" in _origins
if _allow_all:
    logger.warning("CORS_ORIGINS berisi '*': credentials dimatikan. Isi daftar origin eksplisit di production.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allow_all else _origins,
    allow_credentials=not _allow_all,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)

app.include_router(endpoints_auth.router, prefix=API_PREFIX)
app.include_router(endpoints_devices.router, prefix=API_PREFIX)
router_status.update({"endpoints_auth": "ok", "endpoints_devices": "ok"})
_include_feature_routers(app)


_STATIC = Path(__file__).resolve().parent.parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(_STATIC / "index.html")


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    body: dict = {"status": "ok", "version": settings.app_version, "app": settings.app_name}
    if not settings.is_production:
        body["routers"] = dict(router_status)
    return body
