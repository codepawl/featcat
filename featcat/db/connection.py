"""SQLAlchemy engine + session factory.

Phase 1: SQLite only. Postgres branch lands in Phase 2.
"""

from __future__ import annotations

import os
from typing import Literal

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

Backend = Literal["sqlite", "postgres"]


def resolve_backend() -> Backend:
    """Resolve the configured DB backend from env. Phase 1 only honours sqlite."""
    raw = os.environ.get("FEATCAT_DB_BACKEND", "sqlite").lower().strip()
    if raw == "postgres":
        # Postgres support arrives in Phase 2; for now we surface a clear error
        # rather than silently falling back, so a misconfigured deploy is loud.
        raise NotImplementedError(
            "FEATCAT_DB_BACKEND=postgres requires Phase 2 of the migration. Use 'sqlite' (default) until Phase 2 lands."
        )
    if raw not in ("sqlite",):
        raise ValueError(f"Unsupported FEATCAT_DB_BACKEND={raw!r}; expected 'sqlite' or 'postgres'.")
    return "sqlite"


def make_engine(db_path: str) -> Engine:
    """Create a SQLAlchemy engine for the given SQLite database path.

    StaticPool is used so the engine shares one underlying connection across the
    sessionmaker — this matches the legacy ``sqlite3.connect(check_same_thread=False)``
    semantics where a single connection is multiplexed across threads.

    ``detect_types=PARSE_DECLTYPES`` is intentionally NOT passed here. The legacy
    ``self.conn`` in LocalBackend keeps that flag (so ``sqlite3.register_converter``
    hooks for TIMESTAMP fire and existing callers receive ``datetime`` objects).
    SQLAlchemy does its own type conversion via ORM column types, and double-decoding
    via the registered converter would raise ``TypeError: fromisoformat: argument
    must be str``.
    """
    url = f"sqlite:///{db_path}"
    return create_engine(
        url,
        connect_args={
            "check_same_thread": False,
            "timeout": 30.0,
        },
        poolclass=StaticPool,
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


__all__ = [
    "Backend",
    "make_engine",
    "make_session_factory",
    "resolve_backend",
]
