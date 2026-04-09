# Stage 1: Build frontend
FROM node:20-slim AS frontend
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci
COPY web/ ./
RUN DOCKER_BUILD=1 npm run build

# Stage 2: Python app
FROM python:3.12-slim
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install featcat with server extras
COPY . /app/
# Copy built frontend into static directory
COPY --from=frontend /web/dist /app/featcat/server/static/
RUN uv pip install --system --no-cache-dir -e ".[server]"

# Create default catalog directory
RUN mkdir -p /data

# Expose API + Web UI port
EXPOSE 8000

# Default config via env vars
ENV FEATCAT_CATALOG_DB_PATH=/data/catalog.db
ENV FEATCAT_LLM_BACKEND=llamacpp
ENV FEATCAT_LLAMACPP_URL=http://llm:8080
ENV FEATCAT_LLM_MODEL=qwen3.5-0.8b

# Init catalog on first run, then start server
CMD ["sh", "-c", "featcat init 2>/dev/null; featcat serve --host 0.0.0.0 --port 8000"]
