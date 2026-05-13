# Stage 1: Build frontend
FROM oven/bun:1 AS frontend

ARG HTTP_PROXY=
ARG HTTPS_PROXY=
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY}

WORKDIR /web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY web/ ./
RUN DOCKER_BUILD=1 bun run build

# Stage 2: Python app
FROM python:3.12-slim
WORKDIR /app

# Image version. Built by `make docker-build`, which derives this from
# `featcat/__init__.py` (the single source of truth that Hatch also reads
# for PyPI). Override at build time: `--build-arg VERSION=x.y.z`.
ARG VERSION=0.4.0
ENV FEATCAT_VERSION=$VERSION

LABEL org.opencontainers.image.title="featcat" \
      org.opencontainers.image.description="AI-powered Feature Catalog with CLI, TUI, REST API, and Web UI" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.source="https://github.com/codepawl/featcat" \
      org.opencontainers.image.licenses="MIT"

ARG HTTP_PROXY=
ARG HTTPS_PROXY=

# Make proxy visible to uv during the install step below.
# Both upper and lowercase because different tools read different vars.
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    NO_PROXY=localhost,127.0.0.1 \
    no_proxy=localhost,127.0.0.1

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install featcat with server extras
COPY . /app/
# Copy built frontend into static directory
COPY --from=frontend /web/dist /app/featcat/server/static/
RUN uv pip install --system --no-cache-dir -e ".[server]"

# Clear proxy so the runtime container doesn't inherit it
# (llm service is internal, talking to it via proxy would break)
ENV HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy=

# Create default catalog directory
RUN mkdir -p /data

# Expose API + Web UI port
EXPOSE 8000

# Default config via env vars
ENV FEATCAT_CATALOG_DB_PATH=/data/catalog.db
ENV FEATCAT_LLM_BACKEND=llamacpp
ENV FEATCAT_LLAMACPP_URL=http://llm:8080
ENV FEATCAT_LLM_MODEL=gemma-4-E2B-it

# Apply migrations (Alembic — works for both sqlite and postgres backends via
# FEATCAT_DB_BACKEND/FEATCAT_DB_URL), seed defaults, then start server.
# `featcat init` is kept after `alembic upgrade head` so the legacy ALTER TABLE
# shims still run for older sqlite catalogs; on a fresh DB it's a fast no-op.
CMD ["sh", "-c", "alembic upgrade head && (featcat init 2>/dev/null || true) && featcat serve --host 0.0.0.0 --port 8000"]