#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.yml"

if ! docker info >/dev/null 2>&1; then
  cat >&2 <<'EOF'
Docker is required for the optional MinIO smoke, but the Docker daemon is not reachable.

Start Docker, then rerun:
  scripts/smoke_training_dataset_s3.sh

On Linux, this usually means starting the service:
  sudo systemctl start docker

This smoke is optional; normal unit tests do not require MinIO or Docker.
EOF
  exit 1
fi

BUCKET="${FEATCAT_S3_SMOKE_BUCKET:-featcat-smoke}"
PREFIX="${FEATCAT_S3_SMOKE_PREFIX:-training-dataset}"

export MINIO_BUCKET="${BUCKET}"
export MINIO_ROOT_USER="${MINIO_ROOT_USER:-featcat}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-featcat-secret}"
export FEATCAT_S3_ENDPOINT_URL="${FEATCAT_S3_ENDPOINT_URL:-http://localhost:9000}"
export FEATCAT_S3_ACCESS_KEY_ID="${FEATCAT_S3_ACCESS_KEY_ID:-${MINIO_ROOT_USER}}"
export FEATCAT_S3_SECRET_ACCESS_KEY="${FEATCAT_S3_SECRET_ACCESS_KEY:-${MINIO_ROOT_PASSWORD}}"
export FEATCAT_S3_REGION="${FEATCAT_S3_REGION:-us-east-1}"
export FEATCAT_S3_FORCE_PATH_STYLE="${FEATCAT_S3_FORCE_PATH_STYLE:-true}"

entity_uri="s3://${BUCKET}/${PREFIX}/entities.parquet"
source_uri="s3://${BUCKET}/${PREFIX}/features.parquet"
output_uri="s3://${BUCKET}/${PREFIX}/training.parquet"

docker compose -f "${COMPOSE_FILE}" --profile minio up -d minio
docker compose -f "${COMPOSE_FILE}" --profile minio run --rm minio-create-bucket

uv --cache-dir /tmp/uv-cache run python - "${BUCKET}" "${PREFIX}" <<'PY'
from __future__ import annotations

import os
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow.fs import S3FileSystem

bucket = sys.argv[1]
prefix = sys.argv[2]
endpoint = os.environ["FEATCAT_S3_ENDPOINT_URL"]
scheme = "https"
endpoint_override = endpoint
if endpoint.startswith("http://"):
    scheme = "http"
    endpoint_override = endpoint.removeprefix("http://")
elif endpoint.startswith("https://"):
    endpoint_override = endpoint.removeprefix("https://")

fs = S3FileSystem(
    access_key=os.environ["FEATCAT_S3_ACCESS_KEY_ID"],
    secret_key=os.environ["FEATCAT_S3_SECRET_ACCESS_KEY"],
    region=os.environ["FEATCAT_S3_REGION"],
    endpoint_override=endpoint_override,
    scheme=scheme,
    force_virtual_addressing=False,
)

entity = pa.table(
    {
        "user_id": pa.array([1, 2, 1]),
        "event_ts": pa.array(["2026-01-03", "2026-01-03", "2026-01-05"]),
        "label": pa.array([0, 1, 1]),
    }
)
source = pa.table(
    {
        "user_id": pa.array([1, 1, 2, 2]),
        "event_ts": pa.array(["2026-01-01", "2026-01-04", "2026-01-01", "2026-01-04"]),
        "score": pa.array([10, 40, 20, 999]),
        "country": pa.array(["US", "US", "CA", "CA"]),
    }
)

pq.write_table(entity, f"{bucket}/{prefix}/entities.parquet", filesystem=fs)
pq.write_table(source, f"{bucket}/{prefix}/features.parquet", filesystem=fs)
PY

uv --cache-dir /tmp/uv-cache run featcat dataset build \
  --entities "${entity_uri}" \
  --source "${source_uri}" \
  --entity-key user_id \
  --entity-timestamp event_ts \
  --source-timestamp event_ts \
  --features score,country \
  --output "${output_uri}" \
  --json

uv --cache-dir /tmp/uv-cache run python - "${BUCKET}" "${PREFIX}" <<'PY'
from __future__ import annotations

import os
import sys

import pyarrow.parquet as pq
from pyarrow.fs import S3FileSystem

bucket = sys.argv[1]
prefix = sys.argv[2]
endpoint = os.environ["FEATCAT_S3_ENDPOINT_URL"]
scheme = "https"
endpoint_override = endpoint
if endpoint.startswith("http://"):
    scheme = "http"
    endpoint_override = endpoint.removeprefix("http://")
elif endpoint.startswith("https://"):
    endpoint_override = endpoint.removeprefix("https://")

fs = S3FileSystem(
    access_key=os.environ["FEATCAT_S3_ACCESS_KEY_ID"],
    secret_key=os.environ["FEATCAT_S3_SECRET_ACCESS_KEY"],
    region=os.environ["FEATCAT_S3_REGION"],
    endpoint_override=endpoint_override,
    scheme=scheme,
    force_virtual_addressing=False,
)

table = pq.read_table(f"{bucket}/{prefix}/training.parquet", filesystem=fs)
data = table.to_pydict()
assert data["score"] == [10, 20, 40], data
assert data["country"] == ["US", "CA", "US"], data
PY

echo "S3 training dataset smoke passed: ${output_uri}"
