"""Alembic migration environment for featcat.

Resolution order for the database URL:
1. ``FEATCAT_DB_URL`` env var (explicit override; lands in Phase 2 for Postgres)
2. The ``sqlalchemy.url`` value from ``alembic.ini`` (default: local SQLite)

``target_metadata`` points at ``featcat.db.models.Base.metadata`` so
``alembic revision --autogenerate`` diffs the live DB against the ORM models.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure ``featcat`` is importable when running ``alembic`` from the repo root.
# ``prepend_sys_path = .`` in alembic.ini covers this; the explicit import below
# fails fast with a clearer error if the package is missing.
from featcat.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with FEATCAT_DB_URL if set (used by Docker entrypoint
# and any operator-driven migration runs).
_env_url = os.environ.get("FEATCAT_DB_URL")
if _env_url:
    config.set_main_option("sqlalchemy.url", _env_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # render_as_batch makes ALTER TABLE work for SQLite (which lacks native
        # ALTER COLUMN); harmless for Postgres.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
