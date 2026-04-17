"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from ..catalog.local import LocalBackend
from ..config import load_settings

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize backend and LLM on startup, close on shutdown."""
    settings = load_settings()
    backend = LocalBackend(settings.catalog_db_path)
    backend.init_db()
    app.state.backend = backend
    app.state.settings = settings

    logger.info("Static dir: %s, exists: %s", STATIC_DIR, STATIC_DIR.is_dir())
    if STATIC_DIR.is_dir():
        logger.info("Static contents: %s", [p.name for p in STATIC_DIR.iterdir()])

    # Try to create LLM (may fail if server not running)
    try:
        from ..llm import create_llm

        llm = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.llamacpp_url,
            timeout=settings.llm_timeout,
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

    # Register API routes
    from .routes.ai import router as ai_router
    from .routes.docs import router as docs_router
    from .routes.export import router as export_router
    from .routes.features import router as features_router
    from .routes.groups import router as groups_router
    from .routes.health import router as health_router
    from .routes.jobs import router as jobs_router
    from .routes.monitor import router as monitor_router
    from .routes.scan import router as scan_router
    from .routes.sources import router as sources_router
    from .routes.usage import router as usage_router
    from .routes.versions import router as versions_router

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(sources_router, prefix="/api/sources", tags=["sources"])
    app.include_router(features_router, prefix="/api/features", tags=["features"])
    app.include_router(docs_router, prefix="/api/docs", tags=["docs"])
    app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])
    app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(groups_router, prefix="/api/groups", tags=["groups"])
    app.include_router(usage_router, prefix="/api/usage", tags=["usage"])
    app.include_router(scan_router, prefix="/api/scan-bulk", tags=["scan"])
    app.include_router(export_router, prefix="/api/export", tags=["export"])
    app.include_router(versions_router, prefix="/api/versions", tags=["versions"])

    # Mount static assets (js, css) under /assets if present
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA routes — always registered, return 404 if static files missing
    @app.get("/")
    async def serve_root():
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        return Response(content="Web UI not built. Run: cd web && npm run build", status_code=404)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Serve actual static files (e.g. favicon.ico, vite.svg)
        file_path = STATIC_DIR / full_path
        if full_path and file_path.is_file():
            return FileResponse(file_path)
        # SPA fallback: return index.html for React Router
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index, media_type="text/html")
        return Response(content="Web UI not built. Run: cd web && npm run build", status_code=404)

    return app
