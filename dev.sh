#!/usr/bin/env bash
set -e

# Find node from nvm without sourcing nvm.sh (avoids recursive function bug)
NODE_DIR="$(ls -d "$HOME/.nvm/versions/node/"* 2>/dev/null | sort -V | tail -1)"
if [ -n "$NODE_DIR" ]; then
  export PATH="$NODE_DIR/bin:$PATH"
fi

# Verify required CLI tools
if ! command -v featcat >/dev/null 2>&1; then
  echo "error: 'featcat' not on PATH. Run 'make install' (or activate your venv) first." >&2
  exit 1
fi
if ! command -v bun >/dev/null 2>&1; then
  echo "error: 'bun' not on PATH. Install bun: https://bun.sh" >&2
  exit 1
fi

# Cleanup container + child processes on exit. Registered early so Ctrl+C
# during model download / health-wait still tears the container down.
trap 'docker stop featcat-llm 2>/dev/null || true; kill 0 2>/dev/null || true' EXIT

# --- One-time setup ---

# Download GGUF model if not present (atomic via .part to avoid corrupt files)
MODEL_FILE="deploy/models/gemma-4-E2B-it-Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
  echo "Downloading GGUF model..."
  mkdir -p deploy/models
  PROXY_FLAG=""
  if [ -n "$HTTP_PROXY" ]; then
    PROXY_FLAG="-x $HTTP_PROXY"
  fi
  curl --fail $PROXY_FLAG -L -o "${MODEL_FILE}.part" \
    "https://huggingface.co/google/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
  mv "${MODEL_FILE}.part" "$MODEL_FILE"
fi

# Start llama.cpp server via Docker if not already running
if ! curl -s http://localhost:8080/health >/dev/null 2>&1; then
  echo "Starting llama.cpp server..."
  docker rm -f featcat-llm 2>/dev/null || true
  docker run -d --rm --name featcat-llm \
    -v "$(pwd)/deploy/models:/models" \
    -p 8080:8080 \
    ghcr.io/ggml-org/llama.cpp:server \
    --model /models/gemma-4-E2B-it-Q4_K_M.gguf \
    --host 0.0.0.0 --port 8080 \
    --threads 4 --ctx-size 4096 --batch-size 256 \
    --no-mmap --jinja

  echo "Waiting for LLM server..."
  until curl -s http://localhost:8080/health >/dev/null 2>&1; do
    sleep 1
  done
  echo "LLM server ready."
else
  echo "LLM server already running on :8080"
fi

# Init catalog + import sample data on first run only.
if [ ! -f catalog.db ]; then
  echo "Initializing catalog..."
  featcat init
  echo "Importing sample data..."
  featcat add tests/fixtures/user_behavior_30d.parquet --owner dev --skip-docs
  featcat add tests/fixtures/device_performance.parquet --owner dev --skip-docs
fi

# Install frontend deps on first run
if [ ! -d web/node_modules ]; then
  echo "Installing frontend deps..."
  (cd web && bun install)
fi

# --- Start services ---

echo "Starting backend (port 8000)..."
featcat serve --reload --port 8000 &

echo "Starting frontend (port 5173)..."
(cd web && bun run dev) &

# Exit as soon as either side dies (don't leave the user with half a stack).
wait -n
exit_code=$?
exit "$exit_code"
