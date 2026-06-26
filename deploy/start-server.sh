#!/bin/sh
set -eu

echo "featcat startup: applying database migrations"
alembic upgrade head

echo "featcat startup: initializing feature store metadata"
featcat init

echo "featcat startup: serving API on ${FEATCAT_SERVER_HOST:-0.0.0.0}:${FEATCAT_SERVER_PORT:-8000}"
exec featcat serve --host "${FEATCAT_SERVER_HOST:-0.0.0.0}" --port "${FEATCAT_SERVER_PORT:-8000}"
