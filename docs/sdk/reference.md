# SDK reference

The `featcat-client` package is a synchronous HTTP client for notebooks and batch jobs. It wraps the REST API and returns Pydantic models.

## Client

```python
from featcat_client import FeatCatClient

client = FeatCatClient(
    base_url="http://localhost:8000",
    actor="my-notebook",
    connect_timeout=5.0,
    read_timeout=30.0,
    max_retries=3,
)
```

`actor` is sent as `X-Featcat-Actor` for traceability. It is not an auth credential.

## Methods

| Method | Returns | Endpoint |
|---|---|---|
| `list_sources()` | `list[DataSource]` | `GET /api/sources` |
| `get_source(name)` | `DataSource` | `GET /api/sources/{name}` |
| `list_features(...)` | `list[Feature]` | `GET /api/features` |
| `get_feature(name)` | `Feature` | `GET /api/features/by-name?name=...` |
| `get_path(name)` | `str` | feature lookup + source lookup |
| `read_feature(name)` | `polars.DataFrame` | feature lookup + parquet read |
| `search(query, limit=50)` | `list[Feature]` | `GET /api/features?search=...` |
| `find_similar(name, top_k=10, threshold=0.3)` | `list[Feature]` | `GET /api/features/by-name/similar` |
| `get_feature_usage(name)` | `FeatureUsage` | `GET /api/usage/feature?name=...` |
| `list_groups(project=None)` | `list[FeatureGroup]` | `GET /api/groups` |
| `get_group(name)` | `FeatureGroupDetail` | `GET /api/groups/{name}` |

## Models and errors

The public model types are `DataSource`, `Feature`, `FeatureGroup`, `FeatureGroupDetail`, and `FeatureUsage`.

All SDK exceptions inherit from `FeatCatError`:

| Error | Meaning |
|---|---|
| `ConnectionError` | Server unreachable after retries |
| `ServerError` | Non-2xx response that is not mapped to a typed not-found error |
| `FeatureNotFound` | Feature lookup returned 404 |
| `GroupNotFound` | Group lookup returned 404 |

Use the client as a context manager or call `close()` when reusing it in a long-running process.
