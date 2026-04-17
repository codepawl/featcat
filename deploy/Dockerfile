# Stage 1: Build frontend
FROM node:20-slim AS frontend

ARG HTTP_PROXY=
ARG HTTPS_PROXY=

WORKDIR /web
COPY web/package.json web/package-lock.json* ./

# Only configure npm proxy if provided
RUN if [ -n "$HTTP_PROXY" ]; then \
      npm config set proxy "$HTTP_PROXY" && \
      npm config set https-proxy "$HTTPS_PROXY"; \
    fi && \
    npm ci

COPY web/ ./
RUN DOCKER_BUILD=1 npm run build

# Stage 2: Python app
FROM python:3.12-slim
WORKDIR /app

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

# Init catalog on first run, then start server
CMD ["sh", "-c", "featcat init 2>/dev/null; featcat serve --host 0.0.0.0 --port 8000"]