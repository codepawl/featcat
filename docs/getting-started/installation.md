# Installation

featcat ships as a Python package plus an optional Docker stack. Three install paths:

- **Local development** — `uv pip install -e .` against a clone, talks to a local SQLite catalog.
- **Production via Docker Compose** — recommended for team usage; brings up Postgres + the API + the LLM + (optionally) Celery workers.
- **SDK only on a notebook host** — install the lightweight `featcat-client` package and point it at an existing server.

## Quickstart (recommended)

Fastest path to a running featcat:

```bash
featcat quickstart            # writes ./featcat-deploy/ with sane defaults
cd featcat-deploy
docker compose up -d
featcat doctor                # verify reachability
```

`featcat quickstart` writes a complete deployment directory (`docker-compose.yml`, `.env`, `.gitignore`, `README.md`) with Postgres as the backend, port 8000 for the server, `./data` as the host data directory, and the default Gemma model.

For an interactive walkthrough that lets you pick backend, port, data dir, and LLM model:

```bash
featcat setup
```

Both commands refuse to clobber a non-empty target (use `--target` to point them at an alternate directory).

## Requirements

- **Python**: 3.10+
- **`uv`**: 0.4+ — the project uses `uv` for dependency management. Install via `curl -LsSf https://astral.sh/uv/install.sh | sh` if you don't have it.
- **Docker**: 24+ for the production path (optional otherwise).
- **Disk**: ~200 MB for the base install. With the optional `[embeddings]` extra you also pull `torch` (~1 GB) for the sentence-transformers model.

## Local development install

```bash
git clone https://github.com/codepawl/featcat.git
cd featcat
make install            # uv pip install -e ".[dev,tui,s3,server]" + pre-commit hooks
featcat init            # creates ./catalog.db (SQLite)
featcat serve --host 0.0.0.0 --port 8000
```

Optional extras (install only what you need):

| Extra | Adds | When you need it |
|---|---|---|
| `[server]` | FastAPI + uvicorn + APScheduler | Running the API/web UI |
| `[tui]` | Textual | The terminal UI (`featcat ui`) |
| `[s3]` | s3fs | Sources at `s3://…` paths |
| `[embeddings]` | sentence-transformers + torch | Vector similarity, NL-query embed-first |
| `[tasks]` | celery + redis + flower | Distributed background jobs |
| `[docs]` | mkdocs-material + mkdocstrings | Building this site locally |
| `[dev]` | pytest, ruff, mypy, etc. | Running `make check` |

`[all]` rolls everything in.

```bash
uv pip install -e ".[all]"
```

## Production via Docker Compose

The bundled compose stack runs **postgres**, **the API server**, and the **llama.cpp LLM** by default. Profiles let you opt into Celery + Flower:

```bash
cd deploy
docker compose up -d                              # API + Postgres + LLM
docker compose --profile tasks up -d              # + Redis + worker + beat + flower
```

Default endpoints:

| Service | Port | Notes |
|---|---|---|
| Web UI / REST API | `:8000` | `featcat-server` container |
| LLM (`llama.cpp`) | `:8080` | Internal; the API calls it on this port |
| Postgres | (internal only) | Not exposed by default — use the API instead |
| Flower | `:5555` | Only with `--profile tasks` |

### Environment variables operators care about

| Var | Default | Purpose |
|---|---|---|
| `FEATCAT_DB_BACKEND` | `postgres` | Set to `sqlite` for single-container dev |
| `FEATCAT_DB_URL` | from compose | Override the connection string |
| `FEATCAT_LLM_MODEL` | `gemma-4-E2B-it` | Model name passed to the API |
| `FEATCAT_LLAMACPP_URL` | `http://llm:8080` | Where the API reaches the LLM |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `featcat` / `featcat_local_only` / `featcat` | Postgres credentials |
| `FEATCAT_SERVER_AUTH_TOKEN` | unset | When set, all `/api/*` requests need `Authorization: Bearer <token>` |
| `FEATCAT_REDIS_URL` | `redis://redis:6379/0` | Only used by the `tasks` profile |

### Postgres bring-up

The first `docker compose up` runs `alembic upgrade head` automatically before launching uvicorn. To migrate an existing SQLite catalog:

```bash
python scripts/migrate_sqlite_to_postgres.py \
    --source /path/to/catalog.db \
    --target postgresql+psycopg2://featcat:featcat_local_only@localhost:5432/featcat
```

The script verifies row counts plus a 10-row content spot-check (JSON-aware for `tags`, `stats`, etc.). It aborts on any mismatch — see [Architecture › Data Layer](../architecture/data.md) *(coming soon)* for the full migration story.

## SDK-only install on notebook hosts

Notebook users don't need the server — just the client:

```bash
uv pip install ./packages/client
# or via git
uv pip install "git+https://github.com/codepawl/featcat.git#subdirectory=packages/client"
```

```python
from featcat_client import FeatCatClient
client = FeatCatClient("http://featcat-server:8000", actor="my-notebook")
```

→ [SDK Quickstart](../sdk/quickstart.md)

## Verify the install

```bash
featcat --version              # CLI sanity check
curl http://localhost:8000/api/health    # API liveness — returns {"status":"ok",...}
```

If the API returns `{"status": "degraded"}`, the LLM container probably isn't up yet — give `llama.cpp` a minute on the first start (it has to load the GGUF into memory). Catalog operations work without the LLM; documentation generation and AI chat don't.

## Troubleshooting

- **`featcat: command not found`** — the editable install put the script in `.venv/bin/`. Either activate the venv (`source .venv/bin/activate`) or run via `uv run featcat ...`.
- **`alembic upgrade head` fails on first run** — make sure the postgres container is `healthy`; the entrypoint waits via `depends_on: condition: service_healthy`. If it timed out, `docker compose logs postgres` usually tells you why.
- **`sentence-transformers` install pulls torch and takes forever** — that's expected (~1 GB). Skip the `[embeddings]` extra if you don't need vector similarity; the existing TF-IDF path still works.

→ [Operations › Troubleshooting](../ops/troubleshooting.md) *(coming soon)*
