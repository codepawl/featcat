"""SQLAlchemy engine + session factory.

Phase 2: dual backend (SQLite + PostgreSQL). Backend resolution:

- ``FEATCAT_DB_BACKEND``: ``"sqlite"`` (default) or ``"postgres"``.
- ``FEATCAT_DB_URL``: optional explicit URL. When unset, defaults are:
  - sqlite:    ``sqlite:///<FEATCAT_CATALOG_DB_PATH>`` (or ``sqlite:///catalog.db``)
  - postgres:  ``postgresql+psycopg2://featcat:featcat@postgres:5432/featcat``

SQLite uses ``StaticPool`` (one shared connection) to match legacy
``sqlite3.connect(check_same_thread=False)`` semantics. Postgres uses
``QueuePool(pool_size=5, max_overflow=10)`` per the Phase 2 spec — sufficient
for the 4-worker uvicorn deployment without tuning.
"""

from __future__ import annotations

import os
from typing import Literal

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

Backend = Literal["sqlite", "postgres"]

DEFAULT_POSTGRES_URL = "postgresql+psycopg2://featcat:featcat_local_only@postgres:5432/featcat"
DEFAULT_SQLITE_PATH = "catalog.db"


def resolve_backend() -> Backend:
    """Resolve the configured DB backend from env var (default sqlite)."""
    raw = os.environ.get("FEATCAT_DB_BACKEND", "sqlite").lower().strip()
    if raw not in ("sqlite", "postgres"):
        raise ValueError(f"Unsupported FEATCAT_DB_BACKEND={raw!r}; expected 'sqlite' or 'postgres'.")
    return raw  # type: ignore[return-value]


def resolve_url(backend: Backend, db_path: str | None = None) -> str:
    """Resolve the SQLAlchemy URL for a given backend.

    Priority: explicit ``FEATCAT_DB_URL`` (only when scheme matches backend) >
    ``db_path`` arg (sqlite only) > backend default.

    The scheme check guards against the deploy footgun where compose sets a
    postgres ``FEATCAT_DB_URL`` by default but the operator runs with
    ``FEATCAT_DB_BACKEND=sqlite``: prefer the resolved-by-backend URL over a
    mismatched explicit URL rather than silently routing to postgres.
    """
    explicit = os.environ.get("FEATCAT_DB_URL")
    if explicit and _url_matches_backend(explicit, backend):
        return explicit
    if backend == "sqlite":
        path = db_path or os.environ.get("FEATCAT_CATALOG_DB_PATH") or DEFAULT_SQLITE_PATH
        return f"sqlite:///{path}"
    return DEFAULT_POSTGRES_URL


def _url_matches_backend(url: str, backend: Backend) -> bool:
    if backend == "sqlite":
        return url.startswith("sqlite:")
    return url.startswith(("postgresql:", "postgresql+", "postgres:"))


def make_engine(backend: Backend | None = None, url: str | None = None, db_path: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured backend.

    All args are optional — when omitted, env vars provide defaults. Pass
    ``db_path`` (sqlite only) when the catalog DB lives at a non-standard path,
    e.g. tests using ``tmp_path / "test.db"``.

    Note on ``connect_args`` for SQLite: ``detect_types=PARSE_DECLTYPES`` is
    intentionally NOT passed. The legacy raw ``self.conn`` in LocalBackend keeps
    that flag (so ``sqlite3.register_converter`` hooks for TIMESTAMP fire and
    callers receive ``datetime`` objects). SQLAlchemy does its own type
    conversion via ORM column types; double-decoding via the registered
    converter would raise ``TypeError: fromisoformat: argument must be str``.
    """
    backend = backend or resolve_backend()
    url = url or resolve_url(backend, db_path=db_path)

    if backend == "sqlite":
        return create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30.0},
            poolclass=StaticPool,
            future=True,
        )

    # postgres
    return create_engine(
        url,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # cheap survival check; avoids stale-conn errors after restart
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


__all__ = [
    "DEFAULT_POSTGRES_URL",
    "DEFAULT_SQLITE_PATH",
    "Backend",
    "make_engine",
    "make_session_factory",
    "resolve_backend",
    "resolve_url",
]
