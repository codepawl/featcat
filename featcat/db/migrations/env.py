"""Alembic migration environment for featcat.

URL resolution delegates to :func:`featcat.db.connection.resolve_url` so the
migration command and the running application share one source of truth:

- ``FEATCAT_DB_URL`` (explicit override) wins when its scheme matches the
  configured backend.
- Otherwise: ``FEATCAT_DB_BACKEND`` (default ``sqlite``) selects backend, then
  ``FEATCAT_CATALOG_DB_PATH`` / postgres default fills in the URL.

``target_metadata`` points at ``featcat.db.models.Base.metadata`` so
``alembic revision --autogenerate`` diffs the live DB against the ORM models.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make sure ``featcat`` is importable when running ``alembic`` from the repo root.
# ``prepend_sys_path = .`` in alembic.ini covers this; the explicit import below
# fails fast with a clearer error if the package is missing.
from featcat.db.connection import resolve_backend, resolve_url  # noqa: E402
from featcat.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Drive the URL through the application's resolver so a misconfigured deploy
# (backend=sqlite with a leftover postgres FEATCAT_DB_URL, or vice versa) lands
# on the same answer as the application.
config.set_main_option("sqlalchemy.url", resolve_url(resolve_backend()))

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
