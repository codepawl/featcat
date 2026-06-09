# featcat-client

Python SDK for the featcat feature catalog server. Lets data scientists pull feature metadata + Parquet data from a notebook in five lines.

## Install

```bash
# From a wheel
uv add ./packages/client
# Or from git
uv add "git+https://github.com/codepawl/featcat.git#subdirectory=packages/client"
```

## Quickstart

```python
from featcat_client import FeatCatClient

client = FeatCatClient(base_url="http://localhost:8000", actor="my-notebook")

# List features by source / tag / dtype
features = client.list_features(source="user_behavior", tag="churn")

# Single feature metadata
feat = client.get_feature("user_behavior.session_count_30d")

# Read a single column as a polars DataFrame
df = client.read_feature("user_behavior.session_count_30d")

# Search
results = client.search("user activity in 30 days")

# Find similar features (TF-IDF cosine)
similar = client.find_similar("user_behavior.session_count_30d", top_k=10)

# Get a group joined into one DataFrame
detail = client.get_group("churn_v2")
df = detail.to_polars(entity_key="user_id")
df_pd = detail.to_pandas(entity_key="user_id")  # requires pip install featcat-client[pandas]
```

### Registry objects + flow

```python
client = FeatCatClient(base_url="http://localhost:8000")

# Registry writes/read
source = client.upsert_source({"name": "events", "path": "/mnt/data/events.parquet"})
entity = client.upsert_entity({"name": "user", "primary_keys": ["user_id"]})
feature_view = client.upsert_feature_view(
    {
        "name": "user_events_all",
        "entity": "user",
        "source_name": "events",
        "feature_names": [
            "events.user_id",
            "events.event_ts",
            "events.event_type",
        ],
    }
)
feature_set = client.upsert_feature_set(
    {
        "name": "user_event_set",
        "target_entity": "user",
        "feature_names": ["events.user_id", "events.event_type"],
    }
)

# Scan and register features for a source
scan = client.scan_source("events")

# One-call onboarding helper
flow = client.flow(
    path="/mnt/data/events.parquet",
    source_name="events",
    entity="user",
    entity_primary_key=["user_id"],
    feature_view=["all:*.user_*", "core:*.event_type"],
    feature_set="user_event_set",
)

flow.feature_set.name
flow.scan_result.features_registered
```

## Configuration

```python
client = FeatCatClient(
    base_url="http://server:8000",
    actor="ds-pipeline-v2",         # sent as X-Featcat-Actor header for traceability
    connect_timeout=5.0,
    read_timeout=30.0,
    max_retries=3,                  # retries on 5xx with exponential backoff
)
```

## Errors

All client-side failures inherit from `FeatCatError`:

- `ConnectionError` — server unreachable after retries
- `ServerError(status_code, body)` — non-2xx the SDK doesn't recognize
- `FeatureNotFound(name)` — 404 on a feature lookup
- `SourceNotFound(name)` — 404 on a source lookup
- `EntityNotFound(name)` — 404 on an entity lookup
- `EntityRelationshipNotFound(name)` — 404 on relationship lookup
- `FeatureViewNotFound(name)` — 404 on feature-view lookup
- `FeatureSetNotFound(name)` — 404 on feature-set lookup
- `BusinessMetricNotFound(name)` — 404 on business-metric lookup
- `GroupNotFound(name)` — 404 on a group lookup

## Notes

- **Auth**: there isn't any. `actor` is opaque metadata for operational traceability; treat it like a User-Agent string, not a credential.
- **Usage logging**: the server auto-logs a `view` action whenever the SDK fetches a feature by name. There's no separate `log_usage` call.
- **DataFrame**: polars is the default. Pandas conversion is opt-in via `[pandas]` extra to keep install lean.
- **Caching**: parquet reads are LRU-cached per process (size 64). Restart the kernel to drop the cache.

## Development

```bash
cd packages/client
uv sync --all-extras
uv run pytest -v
uv run mypy --strict src/
```
