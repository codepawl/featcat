# Installation Guide

[Tiếng Việt](setup-vi.md)

## System Requirements

| Component | Requirement | Required? |
|-----------|-------------|-----------|
| Python | >= 3.10 | Yes |
| llama.cpp server | Docker image or local binary | No (only needed for AI features) |
| OS | Linux, macOS, WSL2 | Yes |
| Disk | ~100MB for model + DB | Yes |

## Step 1: Set Up Python Environment

```bash
# Using uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
cd featcat
uv venv
source .venv/bin/activate
```

## Step 2: Install featcat

```bash
# Basic install (catalog only, no AI)
uv pip install -e .

# Full install with all extras
uv pip install -e ".[dev,tui,server]"
```

Available extras:
- `dev` — pytest, test tools, MinIO testcontainer for S3 tests
- `tui` — Textual terminal UI
- `server` — FastAPI + uvicorn for the REST API and Web UI

> S3 / MinIO support is built into the default install (uses PyArrow's
> bundled S3FileSystem) — no extra needed. Just set `FEATCAT_S3_*` env vars.

## Step 3: Start llama.cpp (Optional but Recommended)

featcat talks to a llama.cpp-compatible HTTP server for AI Discovery, Auto-doc, and NL Query. The development script can start it for you:

```bash
./dev.sh
```

Or run the server yourself and point featcat at it:

```bash
export FEATCAT_LLAMACPP_URL=http://localhost:8080
export FEATCAT_LLM_MODEL=gemma-4-E2B-it
```

## Step 4: Initialize the Catalog

```bash
featcat init
# -> Creates catalog.db in the current directory
```

## Step 5: Import Data

```bash
# Register a local data source
featcat source add device_perf /data/features/device_performance.parquet

# Register an S3/MinIO data source
export FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
export FEATCAT_S3_ACCESS_KEY=minioadmin
export FEATCAT_S3_SECRET_KEY=minioadmin
featcat source add user_logs s3://data-lake/features/user_behavior_30d.parquet

# Scan to auto-create features
featcat source scan device_perf
featcat source scan user_logs
```

## Step 6: Verify

```bash
# Check registered features
featcat feature list

# Check overall system health
featcat doctor
```

## Configuration

featcat reads configuration from environment variables (prefix `FEATCAT_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `FEATCAT_LLM_BACKEND` | `llamacpp` | LLM backend |
| `FEATCAT_LLM_MODEL` | `gemma-4-E2B-it` | Model name |
| `FEATCAT_LLAMACPP_URL` | `http://localhost:8080` | llama.cpp server URL |
| `FEATCAT_CATALOG_DB_PATH` | `catalog.db` | Database path |
| `FEATCAT_MAX_CONTEXT_FEATURES` | `100` | Max features sent to LLM |
| `FEATCAT_LLM_TIMEOUT` | `120` | Timeout (seconds) for LLM requests |
| `FEATCAT_ORG_NAME` | *(none)* | Optional org name injected into AI assistant system prompts (e.g. `Acme Corp`). Default is empty, which keeps the prompts generic. |
| `FEATCAT_S3_ENDPOINT_URL` | *(none)* | S3/MinIO endpoint override (`http://` for plain HTTP) |
| `FEATCAT_S3_ACCESS_KEY` | *(none)* | S3 access key (must pair with `FEATCAT_S3_SECRET_KEY`) |
| `FEATCAT_S3_SECRET_KEY` | *(none)* | S3 secret key (must pair with `FEATCAT_S3_ACCESS_KEY`) |
| `FEATCAT_S3_SESSION_TOKEN` | *(none)* | STS session token (use with access + secret keys) |
| `FEATCAT_S3_REGION` | `us-east-1` | S3 region |
| `FEATCAT_S3_CONNECT_TIMEOUT_MS` | `10000` | S3 connection timeout (milliseconds) |
| `FEATCAT_S3_REQUEST_TIMEOUT_MS` | `60000` | S3 request timeout (milliseconds) |

When `FEATCAT_S3_ACCESS_KEY` / `_SECRET_KEY` are unset, PyArrow's default
credential chain picks up standard `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`AWS_SESSION_TOKEN`, `~/.aws/credentials` profiles, or EC2/ECS/EKS instance
roles. See the admin guide for the full credential resolution order.

Example `.env` file:
```bash
FEATCAT_LLM_MODEL=gemma-4-E2B-it
FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
FEATCAT_S3_ACCESS_KEY=minioadmin
FEATCAT_S3_SECRET_KEY=minioadmin
```
