from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.api.v1 import endpoints_telemetry, endpoints_dispatch, endpoints_sizing, endpoints_agent, endpoints_auth, endpoints_ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pre-load heavy singletons so first request isn't slow
    from app.nilm.classifier import NILMClassifier
    from app.agent.ppo_scheduler import get_ppo_scheduler
    from app.digital_twin.solar_engine import get_solar_engine

    get_solar_engine()
    get_ppo_scheduler()
    yield
    # Shutdown: nothing to tear down for now


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Backend API untuk NOTA LISTRIK — AI Energy Dispatcher & Solar Right-Sizing "
        "Platform untuk UMKM Indonesia. "
        "Mencakup NILM, Digital Twin, RL Dispatch, dan Bankability Scorecard."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(endpoints_auth.router, prefix=API_PREFIX)
app.include_router(endpoints_telemetry.router, prefix=API_PREFIX)
app.include_router(endpoints_dispatch.router, prefix=API_PREFIX)
app.include_router(endpoints_sizing.router, prefix=API_PREFIX)
app.include_router(endpoints_agent.router, prefix=API_PREFIX)
app.include_router(endpoints_ws.router)


_STATIC = Path(__file__).parent.parent / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(_STATIC / "index.html")


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {"status": "ok", "version": settings.app_version, "app": settings.app_name}
