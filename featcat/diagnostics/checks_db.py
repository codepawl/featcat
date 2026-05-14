"""Database checks for ``featcat doctor db``.

Each check is a standalone function. The runner passes ``Settings``; checks
open their own engine via ``featcat.db.connection`` helpers so they stay
free of process-global state.

Postgres-only checks (pgvector, alembic, pool) emit ``SKIP`` on SQLite —
they're not applicable, not failures.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from featcat.db.connection import make_engine, resolve_backend, resolve_url

from .models import CheckResult, CheckStatus
from .runner import register

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from featcat.config import Settings


_REACHABLE_WARN_MS = 500


def _engine(_settings: Settings) -> Engine:
    """Build a fresh engine using the same backend resolution the app uses at runtime."""
    backend = resolve_backend()
    url = resolve_url(backend)
    return make_engine(backend=backend, url=url)


@register("db")
def db_reachable(settings: Settings) -> CheckResult:
    """Open a session, ``SELECT 1``, report latency."""
    backend = resolve_backend()
    started = time.monotonic()
    try:
        engine = _engine(settings)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        elapsed_ms = int((time.monotonic() - started) * 1000)
    except Exception as exc:  # noqa: BLE001 — diagnostic
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return CheckResult(
            name="db_reachable",
            status=CheckStatus.FAIL,
            detail=f"connect failed: {exc}",
            resolution=(
                "Check FEATCAT_DB_BACKEND / FEATCAT_DB_URL or that the postgres service is up"
                if backend == "postgres"
                else "Check FEATCAT_CATALOG_DB_PATH and `featcat init`"
            ),
            duration_ms=elapsed_ms,
        )
    status = CheckStatus.WARN if elapsed_ms > _REACHABLE_WARN_MS else CheckStatus.PASS
    return CheckResult(
        name="db_reachable",
        status=status,
        detail=f"{backend} ({elapsed_ms}ms)",
        resolution="Investigate DB latency" if status is CheckStatus.WARN else None,
        duration_ms=elapsed_ms,
        metadata={"backend": backend, "latency_ms": elapsed_ms},
    )


@register("db")
def db_backend(_settings: Settings) -> CheckResult:
    """Confirm FEATCAT_DB_BACKEND resolves cleanly and matches the active connection."""
    try:
        backend = resolve_backend()
    except ValueError as exc:
        return CheckResult(
            name="db_backend",
            status=CheckStatus.FAIL,
            detail=str(exc),
            resolution="Set FEATCAT_DB_BACKEND to 'sqlite' or 'postgres'",
        )
    return CheckResult(
        name="db_backend",
        status=CheckStatus.PASS,
        detail=f"backend={backend}",
        metadata={"backend": backend},
    )


@register("db")
def db_version(settings: Settings) -> CheckResult:
    """Probe server version. Postgres >=16 PASS; 15 WARN; <15 FAIL. SQLite informational only."""
    backend = resolve_backend()
    try:
        engine = _engine(settings)
        with engine.connect() as conn:
            if backend == "postgres":
                row = conn.execute(text("SELECT current_setting('server_version_num')")).scalar()
                version_num = int(row or 0)
                # 16xxxx → major 16. server_version_num: 160000+ = 16+.
                major = version_num // 10000
                if major >= 16:
                    status = CheckStatus.PASS
                elif major == 15:
                    status = CheckStatus.WARN
                else:
                    status = CheckStatus.FAIL
                return CheckResult(
                    name="db_version",
                    status=status,
                    detail=f"PostgreSQL {major}",
                    resolution="Upgrade to PostgreSQL 16+" if status is not CheckStatus.PASS else None,
                    metadata={"major": major, "server_version_num": version_num},
                )
            # sqlite — always PASS, version is informational
            row = conn.execute(text("SELECT sqlite_version()")).scalar()
            return CheckResult(
                name="db_version",
                status=CheckStatus.PASS,
                detail=f"SQLite {row}",
                metadata={"version": str(row)},
            )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_version",
            status=CheckStatus.FAIL,
            detail=f"version probe failed: {exc}",
        )


@register("db")
def db_pgvector(settings: Settings) -> CheckResult:
    """Confirm the pgvector extension is installed. SKIP on SQLite."""
    backend = resolve_backend()
    if backend != "postgres":
        return CheckResult(
            name="db_pgvector",
            status=CheckStatus.SKIP,
            detail="not applicable on sqlite",
        )
    try:
        engine = _engine(settings)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'")).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_pgvector",
            status=CheckStatus.FAIL,
            detail=f"pgvector probe failed: {exc}",
        )
    if row is None:
        return CheckResult(
            name="db_pgvector",
            status=CheckStatus.FAIL,
            detail="pgvector extension not installed",
            resolution="Use the pgvector/pgvector:pg16 image or run CREATE EXTENSION vector;",
        )
    return CheckResult(
        name="db_pgvector",
        status=CheckStatus.PASS,
        detail=f"pgvector v{row}",
        metadata={"version": str(row)},
    )


@register("db")
def db_alembic(settings: Settings) -> CheckResult:
    """Read ``alembic_version.version_num``. SKIP on SQLite (no Alembic on that path)."""
    backend = resolve_backend()
    if backend != "postgres":
        return CheckResult(
            name="db_alembic",
            status=CheckStatus.SKIP,
            detail="alembic not used on sqlite",
        )
    try:
        engine = _engine(settings)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_alembic",
            status=CheckStatus.FAIL,
            detail=f"alembic_version probe failed: {exc}",
            resolution="Run `alembic upgrade head`",
        )
    if not row:
        return CheckResult(
            name="db_alembic",
            status=CheckStatus.FAIL,
            detail="alembic_version table empty",
            resolution="Run `alembic upgrade head`",
        )
    return CheckResult(
        name="db_alembic",
        status=CheckStatus.PASS,
        detail=f"version={row}",
        metadata={"version_num": str(row)},
    )


@register("db")
def db_catalog_stats(settings: Settings) -> CheckResult:
    """Verify the catalog has registered sources/features.

    Empty catalog is ``WARN`` (could be a fresh install). Schema corruption
    or query failure is ``FAIL``.
    """
    try:
        from featcat.catalog.factory import get_backend

        backend = get_backend()
        stats = backend.get_catalog_stats()
        sources = int(stats.get("sources", 0))
        features = int(stats.get("features", 0))
        backend.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_catalog_stats",
            status=CheckStatus.FAIL,
            detail=f"stats query failed: {exc}",
        )
    if sources == 0 and features == 0:
        return CheckResult(
            name="db_catalog_stats",
            status=CheckStatus.WARN,
            detail="empty catalog (0 sources, 0 features)",
            resolution="Add a source: featcat source add <name> <path>",
            metadata={"sources": 0, "features": 0},
        )
    return CheckResult(
        name="db_catalog_stats",
        status=CheckStatus.PASS,
        detail=f"{sources} source(s), {features} feature(s)",
        metadata={"sources": sources, "features": features},
    )


@register("db")
def db_pool(settings: Settings) -> CheckResult:
    """Connection-pool capacity check. SKIP on SQLite (NullPool, no usage notion)."""
    backend = resolve_backend()
    if backend != "postgres":
        return CheckResult(
            name="db_pool",
            status=CheckStatus.SKIP,
            detail="sqlite uses NullPool",
        )
    try:
        engine = _engine(settings)
        # SQLAlchemy's QueuePool exposes checkedout() — count of borrowed connections —
        # and size() — base pool size. Touching it forces lazy init.
        with engine.connect():
            pass
        pool = engine.pool
        checkedout = pool.checkedout()  # type: ignore[attr-defined]
        size = pool.size()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_pool",
            status=CheckStatus.FAIL,
            detail=f"pool probe failed: {exc}",
        )
    capacity = max(size, 1)
    pct = checkedout / capacity
    if pct >= 0.8:
        status = CheckStatus.FAIL
    elif pct >= 0.5:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.PASS
    return CheckResult(
        name="db_pool",
        status=status,
        detail=f"{checkedout}/{size} connections in use",
        resolution="Investigate connection leaks or raise pool_size" if status is not CheckStatus.PASS else None,
        metadata={"checked_out": checkedout, "size": size},
    )


@register("db")
def db_cache_stats(settings: Settings) -> CheckResult:
    """LLM response cache health: active vs. expired entry counts.

    Informational only — never fails the doctor. Falls back to ``SKIP`` if the
    cache file isn't accessible (e.g. remote-backend mode).
    """
    cache_path = settings.catalog_db_path
    if not Path(cache_path).exists():
        return CheckResult(
            name="db_cache_stats",
            status=CheckStatus.SKIP,
            detail=f"catalog file not at {cache_path}",
        )
    try:
        from featcat.utils.cache import ResponseCache

        cache = ResponseCache(cache_path)
        stats = cache.stats()
        cache.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="db_cache_stats",
            status=CheckStatus.SKIP,
            detail=f"cache unavailable: {exc}",
        )
    return CheckResult(
        name="db_cache_stats",
        status=CheckStatus.PASS,
        detail=f"{stats.get('active', 0)} active, {stats.get('expired', 0)} expired",
        metadata=dict(stats),
    )
