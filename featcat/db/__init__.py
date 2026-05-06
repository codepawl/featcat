"""SQLAlchemy ORM, connection layer, and Alembic migrations for the catalog DB.

Phase 1 of the SQLite -> PostgreSQL migration: foundation only.
- Models here are the schema source of truth.
- `Base.metadata.create_all()` is used for fresh DBs (tests, new installs).
- Alembic migrations live in `featcat/db/migrations/` and are the change vehicle going forward.
- LocalBackend in `featcat/catalog/local.py` still exposes a raw sqlite3 connection
  for scheduler/route/CLI compatibility; that gets cleaned up in Phase 3.
"""

from __future__ import annotations

from .models import Base

__all__ = ["Base"]
