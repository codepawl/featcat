# Local development setup

This page is for people working *on* featcat. End-user installation is at [Getting Started › Installation](../getting-started/installation.md).

## Prerequisites

- **Python 3.10+** (3.12 used in CI)
- **uv** — fast Python package manager. Install: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Bun** — JS runtime + package manager. Install: `curl -fsSL https://bun.sh/install | bash`
- **Docker + Compose** — for postgres and llama.cpp during integration testing
- **Make** — recipes are in the `Makefile`

Optional but useful:

- **direnv** — auto-loads `.env` per project
- **gh** — for opening PRs from the CLI

## First-time clone

```bash
git clone git@github.com:codepawl/featcat.git
cd featcat
make install
# uv pip install -e ".[dev,tui,s3,server]"
# pre-commit install
```

`make install` does:

1. Editable install of the package + all dev extras
2. Installs `pre-commit` hooks (ruff, ruff-format, mypy quick checks)

Optional extras you may want:

```bash
uv pip install -e ".[embeddings]"   # sentence-transformers (heavy, ~500MB)
uv pip install -e ".[tasks]"        # celery + redis client
uv pip install -e ".[docs]"         # mkdocs-material + plugins
uv pip install -e ".[all]"          # everything
```

The default `make install` deliberately doesn't pull `[embeddings]` or `[tasks]` because most contributors don't need them and they're slow to install.

## Web UI

```bash
cd web
bun install
bun run dev          # :5173 with /api proxy to :8000
```

`bun run build` outputs to `featcat/server/static/`, which the FastAPI app serves at `/`. Run a build at least once before running `featcat serve` so the static dir isn't empty.

## Full local dev stack

`./dev.sh` starts everything you need: downloads the GGUF model, brings up llama.cpp via Docker, initializes the SQLite catalog, and starts the API + frontend dev servers in parallel.

```bash
./dev.sh
# llama.cpp: http://localhost:8080
# featcat API: http://localhost:8000
# vite dev: http://localhost:5173 (proxies /api to :8000)
```

Ctrl-C tears everything down.

If you want PostgreSQL instead of SQLite:

```bash
docker compose -f deploy/docker-compose.yml up -d postgres
export FEATCAT_DB_URL="postgresql+psycopg://featcat:featcat@localhost:5432/featcat"
featcat init
./dev.sh --skip-llm-download   # if you already have the model
```

## Editor setup

VS Code: install the "Python" + "Pylance" + "Ruff" extensions. Workspace settings (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "editor.formatOnSave": true,
  "editor.codeActionsOnSave": {"source.fixAll.ruff": "explicit"},
  "[python]": {"editor.defaultFormatter": "charliermarsh.ruff"},
  "[typescript]": {"editor.defaultFormatter": "biomejs.biome"}
}
```

PyCharm / IntelliJ: configure Project Interpreter to `.venv/bin/python`. Enable Ruff via the Ruff plugin.

## Running the test suite

```bash
make test                                 # full suite
pytest tests/test_catalog.py -v           # one file
pytest tests/test_catalog.py::TestCatalogBackend::test_list_features -v  # one test
pytest -k "test_search" -v                # by name match
pytest --lf                               # last-failed only
make test-cov                             # with coverage report
```

See [Testing](testing.md) for what's where and how to add new tests.

## Checking docs

```bash
make docs-check      # command/env/link consistency, no network
make docs            # MkDocs build; install [docs] first
```

## Pre-commit

Hooks run on every commit. To run manually:

```bash
pre-commit run --all-files
```

Hooks installed: ruff (lint + format), trailing whitespace, end-of-file fixer, YAML check, large-file guard. mypy isn't a pre-commit hook (it's slow); CI runs it via `make type-check`.

## Working with migrations

Add a migration:

```bash
alembic -c featcat/db/alembic.ini revision --autogenerate -m "add user_role column"
# edit the generated file in featcat/db/migrations/versions/
alembic -c featcat/db/alembic.ini upgrade head
```

If you stack a PR on top of staging that has a new head, you'll need to merge heads. See [Troubleshooting › alembic-multi-head](../ops/troubleshooting.md#alembicutilexccommanderror-multiple-head-revisions-are-present).

Cross-dialect: always test SQLite path. Use `op.batch_alter_table(...)` for ALTERs that SQLite can't do natively.

## Branch flow

```
main         <- prod, tagged releases
staging      <- integration; sprint accumulator
feat/X       <- topic branches off staging
fix/X
chore/X
docs/X
```

```bash
git checkout staging && git pull
git checkout -b feat/your-feature
# work
make check                                # lint + type-check + test
git push -u origin feat/your-feature
gh pr create --base staging --fill
```

After merge:

```bash
git checkout staging && git pull
git branch -d feat/your-feature
git push origin --delete feat/your-feature  # usually gh pr merge --delete-branch already did this
```

`main` is touched only when staging is green and you're cutting a release.

## Common environment variables

```bash
FEATCAT_DB_URL=sqlite:///./catalog.db   # or postgresql+psycopg://...
FEATCAT_LLAMACPP_URL=http://localhost:8080
FEATCAT_LLM_BACKEND=llamacpp
FEATCAT_CORS_ORIGINS=http://localhost:5173
FEATCAT_TASKS_BACKEND=apscheduler       # or celery
FEATCAT_SERVER_URL=http://localhost:8000  # makes the CLI hit the API
```

Stash these in a `.env` at repo root. `dev.sh` sources it.

## Related

- **[Style guide](style.md)** — code conventions
- **[Testing](testing.md)** — test layout + patterns
- **[Architecture Overview](../architecture/overview.md)** — what's where
