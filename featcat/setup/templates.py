"""Load and render setup templates with ``str.format`` substitution.

Templates live in ``featcat/templates/setup/`` as static text files with
``{placeholder}`` slots. To dodge Jinja2-style conditionals without adding
a templating dependency, complex optional sections (e.g. the postgres
compose block) are pre-rendered into strings here and injected as
additional placeholders — the top-level template stays logic-free.
"""

from __future__ import annotations

from importlib.resources import files


def render_template(template_name: str, **kwargs: object) -> str:
    """Read a template by basename and substitute ``{placeholder}`` slots.

    Raises ``ValueError`` if a placeholder needed by the template was
    not supplied. The error message names the missing key so the CLI can
    surface it without re-parsing the template.
    """
    template_path = files("featcat.templates") / "setup" / template_name
    raw = template_path.read_text(encoding="utf-8")
    try:
        return raw.format(**kwargs)
    except KeyError as e:
        raise ValueError(
            f"Template {template_name!r} requires placeholder {e.args[0]!r} which was not provided."
        ) from None


POSTGRES_COMPOSE_BLOCK = """\
  postgres:
    image: pgvector/pgvector:pg16
    container_name: featcat-postgres
    environment:
      POSTGRES_USER: ${{POSTGRES_USER:-featcat}}
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-featcat_local_only}}
      POSTGRES_DB: ${{POSTGRES_DB:-featcat}}
    volumes:
      - featcat-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${{POSTGRES_USER:-featcat}} -d ${{POSTGRES_DB:-featcat}}"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped

"""

POSTGRES_FEATCAT_ENV = """\
      - FEATCAT_DB_URL=postgresql+psycopg2://${{POSTGRES_USER:-featcat}}:${{POSTGRES_PASSWORD:-featcat_local_only}}@postgres:5432/${{POSTGRES_DB:-featcat}}
      - POSTGRES_USER=${{POSTGRES_USER:-featcat}}
      - POSTGRES_PASSWORD=${{POSTGRES_PASSWORD:-featcat_local_only}}
      - POSTGRES_DB=${{POSTGRES_DB:-featcat}}
"""

POSTGRES_DEPENDS_ON = """\
      postgres:
        condition: service_healthy
"""
