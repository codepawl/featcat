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

# 2. Start services
echo "Starting Ollama..."
docker compose up -d ollama

# 3. Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama is ready."

# 4. Pull LLM model
echo "Pulling ${LLM_MODEL:-lfm2.5:latest}..."
docker exec featcat-ollama ollama pull "${LLM_MODEL:-lfm2.5:latest}"

# 5. Also pull thinking model for discovery/monitoring
echo "Pulling lfm2.5-thinking..."
docker exec featcat-ollama ollama pull lfm2.5-thinking

# 6. Start featcat
echo "Starting featcat server..."
docker compose up -d featcat

# 7. Wait for featcat
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
