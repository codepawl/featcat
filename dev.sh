#!/usr/bin/env bash
set -e

# Find node from nvm without sourcing nvm.sh (avoids recursive function bug)
NODE_DIR="$(ls -d "$HOME/.nvm/versions/node/"* 2>/dev/null | sort -V | tail -1)"
if [ -n "$NODE_DIR" ]; then
  export PATH="$NODE_DIR/bin:$PATH"
fi

# --- One-time setup ---

# Download GGUF model if not present
MODEL_FILE="deploy/models/gemma-4-E2B-it-Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
  echo "Downloading GGUF model (~533 MB)..."
  mkdir -p deploy/models
  PROXY_FLAG=""
  if [ -n "$HTTP_PROXY" ]; then
    PROXY_FLAG="-x $HTTP_PROXY"
  fi
  curl $PROXY_FLAG -L -o "$MODEL_FILE" \
    "https://huggingface.co/google/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
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
    --threads 4 --ctx-size 2048 --batch-size 256 \
    --flash-attn on --no-mmap --jinja

  echo "Waiting for LLM server..."
  until curl -s http://localhost:8080/health >/dev/null 2>&1; do
    sleep 1
  done
  echo "LLM server ready."
else
  echo "LLM server already running on :8080"
fi

# Init catalog if not exists
if [ ! -f catalog.db ]; then
  echo "Initializing catalog..."
  featcat init
fi

# Import sample data if catalog is empty
FEATURE_COUNT=$(featcat feature list 2>/dev/null | grep -c "│" || echo "0")
if [ "$FEATURE_COUNT" -lt 2 ]; then
  echo "Importing sample data..."
  featcat add tests/fixtures/user_behavior_30d.parquet --owner dev --skip-docs 2>/dev/null || true
  featcat add tests/fixtures/device_performance.parquet --owner dev --skip-docs 2>/dev/null || true
fi

export FEATCAT_LLM_MODEL=gemma-4-E2B-it-Q4_K_M.gguf

# --- Start services ---

trap 'docker stop featcat-llm 2>/dev/null; kill 0' EXIT

echo "Starting backend (port 8000)..."
featcat serve --reload --port 8000 &

echo "Starting frontend (port 5173)..."
cd web && npm run dev &

wait
