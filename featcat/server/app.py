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
from .auth import can_access, resolve_principal

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

    # Try to create LLM (may fail if server not running).
    # Wrapped in CachedLLM so plugin `generate_json` calls (Discovery,
    # Auto-doc, NL Query, Monitoring LLM analysis) populate the shared
    # `llm_cache` SQLite table — same wrapping the CLI does at
    # `featcat/cli.py:_get_llm`. Streaming endpoints (AI Chat's
    # `llm.chat(...)` and the SSE token stream) pass through unchanged,
    # which is intentional: response freshness matters more than cache hits
    # for interactive chat, and tool-call replies aren't deterministic on key.
    try:
        from ..llm import create_llm
        from ..llm.cached import CachedLLM
        from ..utils.cache import ResponseCache

        inner = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.llamacpp_url,
            timeout=settings.llm_timeout,
        )
        cache = ResponseCache(settings.catalog_db_path)
        app.state.llm = CachedLLM(inner, cache)
        app.state.llm_cache = cache
    except Exception:
        app.state.llm = None
        app.state.llm_cache = None

    # Start scheduler unless explicitly disabled for test/headless use.
    if settings.scheduler_enabled:
        try:
            from .scheduler import FeatcatScheduler

            scheduler = FeatcatScheduler(backend=backend, llm=app.state.llm, settings=settings)
            scheduler.setup_default_jobs()
            scheduler.start()
            app.state.scheduler = scheduler
        except Exception:
            app.state.scheduler = None
    else:
        app.state.scheduler = None

    yield

    # Shutdown
    if getattr(app.state, "scheduler", None):
        app.state.scheduler.stop()
    backend.close()


def build_app(*, use_lifespan: bool = True) -> FastAPI:
    """Create the FastAPI application with all routes."""
    app = FastAPI(
        title="featcat",
        description="AI-Powered Feature Catalog API",
        version="0.1.0",
        lifespan=lifespan if use_lifespan else None,
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
    if settings.auth_required or settings.server_auth_token:

        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            path = request.url.path
            if path == "/api/health" or path.startswith("/api/auth"):
                return await call_next(request)
            if not path.startswith("/api/"):
                return await call_next(request)

            principal = resolve_principal(request, settings)
            request.state.principal = principal
            request.state.authenticated = principal is not None

            if (settings.auth_required or settings.server_auth_token) and principal is None:
                return Response(content='{"detail":"Unauthorized"}', status_code=401, media_type="application/json")
            if principal is not None and not can_access(principal, request.method, path):
                return Response(content='{"detail":"Forbidden"}', status_code=403, media_type="application/json")
            return await call_next(request)

    # Register API routes
    from .routes.actions import router as actions_router
    from .routes.admin import router as admin_router
    from .routes.ai import router as ai_router
    from .routes.auth import router as auth_router
    from .routes.bulk import router as bulk_router
    from .routes.business_metrics import router as business_metrics_router
    from .routes.datasets import router as datasets_router
    from .routes.docs import router as docs_router
    from .routes.entities import router as entities_router
    from .routes.entity_relationships import router as entity_relationships_router
    from .routes.export import router as export_router
    from .routes.feature_sets import router as feature_sets_router
    from .routes.feature_views import router as feature_views_router
    from .routes.features import router as features_router
    from .routes.groups import router as groups_router
    from .routes.health import router as health_router
    from .routes.jobs import router as jobs_router
    from .routes.lineage import router as lineage_router
    from .routes.monitor import router as monitor_router
    from .routes.notifications import router as notifications_router
    from .routes.online import router as online_router
    from .routes.scan import router as scan_router
    from .routes.scheduler import router as scheduler_router
    from .routes.search import router as search_router
    from .routes.sources import router as sources_router
    from .routes.usage import router as usage_router
    from .routes.versions import router as versions_router

    app.include_router(health_router, prefix="/api", tags=["health"])
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
    app.include_router(sources_router, prefix="/api/sources", tags=["sources"])
    app.include_router(features_router, prefix="/api/features", tags=["features"])
    app.include_router(entities_router, prefix="/api/entities", tags=["entities"])
    app.include_router(entity_relationships_router, prefix="/api/entity-relationships", tags=["entity-relationships"])
    app.include_router(feature_views_router, prefix="/api/feature-views", tags=["feature-views"])
    app.include_router(feature_sets_router, prefix="/api/feature-sets", tags=["feature-sets"])
    app.include_router(docs_router, prefix="/api/docs", tags=["docs"])
    app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])
    app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(groups_router, prefix="/api/groups", tags=["groups"])
    app.include_router(actions_router, prefix="/api/actions", tags=["actions"])
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(business_metrics_router, prefix="/api/business-metrics", tags=["business-metrics"])
    app.include_router(usage_router, prefix="/api/usage", tags=["usage"])
    app.include_router(scan_router, prefix="/api/scan-bulk", tags=["scan"])
    app.include_router(export_router, prefix="/api/export", tags=["export"])
    app.include_router(datasets_router, prefix="/api/datasets", tags=["datasets"])
    app.include_router(online_router, prefix="/api/online", tags=["online"])
    app.include_router(versions_router, prefix="/api/versions", tags=["versions"])
    app.include_router(lineage_router, prefix="/api/lineage", tags=["lineage"])
    app.include_router(bulk_router, prefix="/api/features/bulk", tags=["bulk"])
    app.include_router(search_router, prefix="/api/search", tags=["search"])
    app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])

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
