#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/featcat-materialize-smoke.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

FEATCAT=(uv --cache-dir "$UV_CACHE_DIR" run featcat)

echo "Smoke workspace: $WORK_DIR"

pushd "$WORK_DIR" >/dev/null

uv --cache-dir "$UV_CACHE_DIR" run python - <<'PY'
import pyarrow as pa
import pyarrow.parquet as pq

table = pa.table(
    {
        "customer_id": [1, 1, 2],
        "event_ts": [
            "2026-05-25T09:00:00Z",
            "2026-05-25T10:00:00Z",
            "2026-05-25T08:00:00Z",
        ],
        "avg_spend_30d": [10.0, 20.0, 30.0],
        "txn_count_30d": [1, 2, 3],
    }
)
pq.write_table(table, "transactions.parquet")
PY

"${FEATCAT[@]}" init
"${FEATCAT[@]}" add transactions.parquet --name transactions --skip-docs
"${FEATCAT[@]}" source update transactions \
  --entity-key customer_id \
  --event-timestamp-column event_ts

"${FEATCAT[@]}" online materialize \
  --source transactions \
  --features avg_spend_30d,txn_count_30d \
  --project churn \
  --feature-view transactions \
  --json > materialize.json

printf '{"customer_id":1}\n{"customer_id":2}\n' > entities.jsonl

"${FEATCAT[@]}" online get \
  --entities entities.jsonl \
  --features transactions.avg_spend_30d,transactions.txn_count_30d \
  --project churn \
  --feature-view transactions \
  --json > online_get.json

uv --cache-dir "$UV_CACHE_DIR" run python - <<'PY'
import json

with open("materialize.json", encoding="utf-8") as fh:
    materialize = json.load(fh)
assert materialize["is_valid"] is True, materialize
assert materialize["requested"] == 4, materialize
assert materialize["written"] == 4, materialize

with open("online_get.json", encoding="utf-8") as fh:
    online = json.load(fh)

rows = online["rows"]
assert [row["entity_key"] for row in rows] == [{"customer_id": 1}, {"customer_id": 2}], online
assert rows[0]["features"] == {
    "transactions.avg_spend_30d": 20.0,
    "transactions.txn_count_30d": 2,
}, online
assert rows[1]["features"] == {
    "transactions.avg_spend_30d": 30.0,
    "transactions.txn_count_30d": 3,
}, online
for row in rows:
    for metadata in row["metadata"].values():
        assert metadata["found"] is True, online
PY

popd >/dev/null

echo "Materialization online smoke passed."
