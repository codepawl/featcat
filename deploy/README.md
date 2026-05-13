# featcat Docker Deployment

## Requirements

- Docker >= 20.10
- Docker Compose >= 2.0

> 🇻🇳 Tiếng Việt: see [README-vi.md](README-vi.md).

## Pre-built Image

Each GitHub Release automatically builds and publishes a multi-arch image
(`linux/amd64` + `linux/arm64`) to GHCR:

```bash
docker pull ghcr.io/codepawl/featcat:latest
```

Available tags: `latest`, `<version>` (for example `0.2.5`), and `<major>.<minor>` (for example `0.2`).

To use the published image instead of building locally, update `docker-compose.yml`:

```yaml
  featcat:
    # build: .                                  # remove this line
    image: ghcr.io/codepawl/featcat:latest      # add this line
```

## First-time Setup

```bash
# Clone the repo
git clone https://github.com/codepawl/featcat.git
cd featcat/deploy

# Create the config file
cp .env.example .env

# Edit DATA_DIR in .env to point at the directory containing Parquet files
nano .env

# Run setup (pull model, start services)
bash setup.sh
```

## Access

- **Web UI:** http://<server-ip>:8000
- **API:** http://<server-ip>:8000/api/health
- **CLI from another machine:**
  ```bash
  uv pip install featcat
  featcat config set server http://<server-ip>:8000
  featcat stats
  ```

## Import Data

```bash
# Copy a Parquet file into DATA_DIR, then:
docker exec featcat-server featcat add /sources/your_file.parquet --owner <name>

# Or import multiple files:
docker exec featcat-server featcat add /sources/ --name my-dataset --owner <name>
```

## Useful Commands

```bash
# View logs
docker compose logs -f featcat

# Restart the server
docker compose restart featcat

# Stop everything
docker compose down

# Bring services back up
docker compose up -d

# Health check
docker exec featcat-server featcat doctor

# View catalog stats
docker exec featcat-server featcat stats

# View scheduled jobs
docker exec featcat-server featcat job list

# Run a manual job
docker exec featcat-server featcat job run monitor_check
```

## Upgrade

```bash
cd featcat
git pull
cd deploy
docker compose build featcat
docker compose up -d
```

## Backup

```bash
# Back up the catalog database
docker exec featcat-server cp /data/catalog.db /sources/backup/catalog-$(date +%Y%m%d).db

# Or copy it from the Docker volume
docker cp featcat-server:/data/catalog.db ./backup/
```

## Configuration

Edit `.env` and restart:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Host directory containing Parquet files | `./data` |
| `FEATCAT_PORT` | Port exposed for the Web UI + API | `8000` |
| `LLM_MODEL` | LLM model filename | `lfm2.5-thinking` |
| `SERVER_AUTH` | API auth token (leave empty for no auth) | _(empty)_ |

## Proxy (Corporate Networks)

If the server sits behind a proxy, set these in `.env` before running `setup.sh`:

```env
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080
```

The proxy is forwarded automatically to both Ollama (for pulling the model) and the featcat container.

**If Ollama still cannot pull the model through the proxy:**
1. Install Ollama directly on the host
2. Pull the model with the proxy set:
   ```bash
   HTTPS_PROXY=http://proxy.example.com:8080 ollama pull lfm2.5-thinking
   ```
3. Mount the model directory into the Ollama container (edit `docker-compose.yml`):
   ```yaml
   ollama:
     volumes:
       - /usr/share/ollama/.ollama:/root/.ollama
   ```

## Troubleshooting

**featcat cannot connect to Ollama:**
```bash
# Check that Ollama is running
docker compose ps
docker compose logs ollama

# Restart Ollama
docker compose restart ollama
```

**Model has not been pulled:**
```bash
docker exec featcat-ollama ollama list
docker exec featcat-ollama ollama pull lfm2.5-thinking
```

**Catalog database is corrupted:**
```bash
# Remove and reinitialize
docker exec featcat-server rm /data/catalog.db
docker compose restart featcat
```