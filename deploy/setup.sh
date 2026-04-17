#!/bin/bash
set -e

echo "=== featcat deployment setup ==="

# 1. Copy env file if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env — edit DATA_DIR before continuing"
    echo "Then re-run this script."
    exit 0
fi

# Load env
source .env

# 2. Download GGUF model if not present
mkdir -p models
MODEL_FILE="models/gemma-4-E2B-it-Q4_K_M.gguf"
if [ ! -f "$MODEL_FILE" ]; then
    echo "Downloading GGUF model (~533 MB)..."
    PROXY_FLAG=""
    if [ -n "$HTTP_PROXY" ]; then
        PROXY_FLAG="-x $HTTP_PROXY"
    fi
    curl $PROXY_FLAG -L -o "$MODEL_FILE" \
        "https://huggingface.co/google/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
    echo "Model downloaded."
else
    echo "Model already exists: $MODEL_FILE"
fi

# 3. Start LLM server
echo "Starting llama.cpp server..."
docker compose up -d llm

# 4. Wait for LLM server to be ready
echo "Waiting for LLM server to start..."
until curl -s http://localhost:8080/health > /dev/null 2>&1; do
    sleep 2
done
echo "LLM server is ready."

# 5. Start featcat
echo "Starting featcat server..."
docker compose up -d featcat

# 6. Wait for featcat
echo "Waiting for featcat server..."
until curl -s http://localhost:${FEATCAT_PORT:-8000}/api/health > /dev/null 2>&1; do
    sleep 2
done

echo ""
echo "=== Setup complete ==="
echo "Web UI:  http://localhost:${FEATCAT_PORT:-8000}"
echo "API:     http://localhost:${FEATCAT_PORT:-8000}/api/health"
echo ""
echo "From other machines:"
echo "  featcat config set server http://$(hostname -I | awk '{print $1}'):${FEATCAT_PORT:-8000}"
echo ""
echo "To import data:"
echo "  docker exec featcat-server featcat add /sources/your_file.parquet --owner yourname"
