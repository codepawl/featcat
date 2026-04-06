FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install featcat with server extras
COPY . /app/
RUN uv pip install --system --no-cache-dir ".[server]"

# Create default catalog directory
RUN mkdir -p /data

# Expose API + Web UI port
EXPOSE 8000

# Default config via env vars
ENV FEATCAT_CATALOG_DB_PATH=/data/catalog.db
ENV FEATCAT_OLLAMA_URL=http://ollama:11434
ENV FEATCAT_LLM_MODEL=lfm2.5-thinking

# Init catalog on first run, then start server
CMD ["sh", "-c", "featcat init 2>/dev/null; featcat serve --host 0.0.0.0 --port 8000"]
