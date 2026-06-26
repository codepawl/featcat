# syntax=docker/dockerfile:1.7
#
# Multi-stage build with a TORCH_VARIANT switch:
#   --build-arg TORCH_VARIANT=cpu   (default — small image, no CUDA libs)
#   --build-arg TORCH_VARIANT=gpu   (CUDA 12.1 build of torch; ~5 GB larger)
#
# Tag convention:
#   nxank4/featcat:latest       built with TORCH_VARIANT=cpu
#   nxank4/featcat:latest-gpu   built with TORCH_VARIANT=gpu
#
# The GPU image still runs on a CPU-only host — `torch.cuda.is_available()`
# just returns False there. Operators pick the image based on disk budget.

ARG TORCH_VARIANT=cpu

# Stage 1: Build frontend (unchanged — torch variant is irrelevant here).
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

# Stage 2: Python base (system setup shared by both torch variants).
FROM python:3.12-slim AS base
WORKDIR /app

# Image version. Built by `make docker-build`, which derives this from
# `featcat/__init__.py` (the single source of truth that Hatch also reads
# for PyPI). Override at build time: `--build-arg VERSION=x.y.z`.
ARG VERSION=0.4.0
ENV FEATCAT_VERSION=$VERSION

LABEL org.opencontainers.image.title="featcat" \
      org.opencontainers.image.description="AI-powered Feature Store with CLI, TUI, REST API, and Web UI" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.source="https://github.com/codepawl/featcat" \
      org.opencontainers.image.licenses="MIT"

ARG HTTP_PROXY=
ARG HTTPS_PROXY=

# Make proxy visible to uv during the install steps below.
# Both upper and lowercase because different tools read different vars.
ENV HTTP_PROXY=${HTTP_PROXY} \
    HTTPS_PROXY=${HTTPS_PROXY} \
    http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY} \
    NO_PROXY=localhost,127.0.0.1 \
    no_proxy=localhost,127.0.0.1

# Install uv for fast dependency management.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Stage 3: Torch dependency layer. Keep this as one conditional stage so the
# legacy Docker builder does not build both CPU and GPU branches.
FROM base AS deps
ARG TORCH_VARIANT=cpu
RUN if [ "$TORCH_VARIANT" = "gpu" ]; then \
      TORCH_INDEX_URL="https://download.pytorch.org/whl/cu121"; \
    else \
      TORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"; \
    fi; \
    uv pip install --system --no-cache-dir --index-url "$TORCH_INDEX_URL" torch

# Stage 4: Final featcat install on top of the chosen torch variant.
FROM deps AS final

# Install featcat with server + embeddings extras. Torch is already
# satisfied from the deps-* parent stage so the resolver does not pull
# the default CUDA wheel even on the CPU build.
COPY . /app/
# Copy built frontend into static directory (kept here so a source change
# does not invalidate the torch layer above).
COPY --from=frontend /web/dist /app/featcat/server/static/
RUN uv pip install --system --no-cache-dir -e ".[server,embeddings,tasks]"

# Clear proxy so the runtime container doesn't inherit it
# (llm service is internal, talking to it via proxy would break).
ENV HTTP_PROXY= HTTPS_PROXY= http_proxy= https_proxy=

# Create default catalog directory and non-root runtime user.
RUN chmod +x /app/deploy/start-server.sh \
    && useradd --create-home --shell /usr/sbin/nologin featcat \
    && mkdir -p /data \
    && chown -R featcat:featcat /data

# Expose API + Web UI port.
EXPOSE 8000

# Default config via env vars.
ENV FEATCAT_CATALOG_DB_PATH=/data/catalog.db
ENV FEATCAT_LLM_BACKEND=llamacpp
ENV FEATCAT_LLAMACPP_URL=http://llm:8080
ENV FEATCAT_LLM_MODEL=gemma-4-E2B-it
ENV PYTHONDONTWRITEBYTECODE=1

USER featcat

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3)); raise SystemExit(0 if data.get('status') == 'ready' else 1)"

# Apply migrations, seed defaults, then start server. Failures are intentionally
# visible so broken deploys do not continue with a half-initialized store.
CMD ["/app/deploy/start-server.sh"]
