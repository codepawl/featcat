# Installation Guide

[Tiếng Việt](setup-vi.md)

## System Requirements

| Component | Requirement | Required? |
|-----------|-------------|-----------|
| Python | >= 3.10 | Yes |
| Ollama | >= 0.1.0 | No (only needed for AI features) |
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
uv pip install -e ".[dev,tui,search,s3]"
```

Available extras:
- `dev` — pytest, test tools
- `tui` — Textual terminal UI
- `search` — rapidfuzz for fuzzy search (fallback when LLM is unavailable)
- `s3` — s3fs for reading Parquet from S3/MinIO

## Step 3: Install Ollama (Optional but Recommended)

Ollama is a local LLM server. Install it to use AI Discovery, Auto-doc, and NL Query.

```bash
# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama
ollama serve

# Pull a model (in another terminal)
ollama pull lfm2.5-thinking
```

> **Tip**: `lfm2.5-thinking` runs well on machines with 8GB RAM.

### Auto-start Ollama (systemd)

```bash
# Create systemd service
sudo tee /etc/systemd/system/ollama.service << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
ExecStart=/usr/local/bin/ollama serve
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now ollama
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
| `FEATCAT_LLM_BACKEND` | `ollama` | LLM backend: `ollama` or `llamacpp` |
| `FEATCAT_LLM_MODEL` | `lfm2.5-thinking` | Model name |
| `FEATCAT_OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `FEATCAT_CATALOG_DB_PATH` | `catalog.db` | Database path |
| `FEATCAT_MAX_CONTEXT_FEATURES` | `100` | Max features sent to LLM |
| `FEATCAT_LLM_TIMEOUT` | `120` | Timeout (seconds) for LLM requests |
| `FEATCAT_S3_ENDPOINT_URL` | *(none)* | S3/MinIO endpoint |
| `FEATCAT_S3_ACCESS_KEY` | *(none)* | S3 access key |
| `FEATCAT_S3_SECRET_KEY` | *(none)* | S3 secret key |
| `FEATCAT_S3_REGION` | `us-east-1` | S3 region |

Example `.env` file:
```bash
FEATCAT_LLM_MODEL=lfm2.5-thinking
FEATCAT_S3_ENDPOINT_URL=http://minio.internal:9000
FEATCAT_S3_ACCESS_KEY=minioadmin
FEATCAT_S3_SECRET_KEY=minioadmin
```
