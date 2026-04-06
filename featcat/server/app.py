"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..catalog.local import LocalBackend
from ..config import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize backend and LLM on startup, close on shutdown."""
    settings = load_settings()
    backend = LocalBackend(settings.catalog_db_path)
    backend.init_db()
    app.state.backend = backend
    app.state.settings = settings

    # Try to create LLM (may fail if Ollama not running)
    try:
        from ..llm import create_llm

        llm = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.ollama_url if settings.llm_backend == "ollama" else settings.llamacpp_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
        app.state.llm = llm
    except Exception:
        app.state.llm = None

    # Start scheduler
    try:
        from .scheduler import FeatcatScheduler

        scheduler = FeatcatScheduler(backend=backend, llm=app.state.llm, settings=settings)
        scheduler.setup_default_jobs()
        scheduler.start()
        app.state.scheduler = scheduler
    except Exception:
        app.state.scheduler = None

    yield

    # Shutdown
    if getattr(app.state, "scheduler", None):
        app.state.scheduler.stop()
    backend.close()


def build_app() -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(
        title="featcat",
        description="AI-Powered Feature Catalog API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Optional auth middleware
    settings = load_settings()
    auth_token = getattr(settings, "server_auth_token", None)
    if auth_token:

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if request.url.path == "/api/health":
                return await call_next(request)
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            if token != auth_token:
                return Response(content='{"detail":"Unauthorized"}', status_code=401, media_type="application/json")
            return await call_next(request)

    # Register routes
    from .routes.ai import router as ai_router
    from .routes.docs import router as docs_router
    from .routes.features import router as features_router
    from .routes.health import router as health_router
    from .routes.monitor import router as monitor_router
    from .routes.sources import router as sources_router

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(sources_router, prefix="/api/sources", tags=["sources"])
    app.include_router(features_router, prefix="/api/features", tags=["features"])
    app.include_router(docs_router, prefix="/api/docs", tags=["docs"])
    app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])
    app.include_router(ai_router, prefix="/api/ai", tags=["ai"])

    from .routes.jobs import router as jobs_router

    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])

    # Serve static Web UI (must be AFTER all /api/* routes)
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
