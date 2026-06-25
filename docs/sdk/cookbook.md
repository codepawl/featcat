# SDK cookbook

Short recipes for common notebook and pipeline workflows.

## Find a candidate feature

```python
from featcat_client import FeatCatClient

client = FeatCatClient("http://localhost:8000", actor="eda-notebook")
matches = client.search("30 day user activity", limit=10)
for feature in matches:
    print(feature.name, feature.dtype, feature.owner)
```

## Read a feature column

```python
df = client.read_feature("user_behavior.session_count_30d")
print(df.head())
```

The SDK resolves the source path from the catalog and reads the parquet locally or through the path scheme the source uses.

## Join a feature group

```python
detail = client.get_group("churn_v2")
df = detail.to_polars(entity_key="user_id")
```

Pass `entity_key` explicitly in production so joins do not depend on auto-detection.

## Compare similar features

```python
base = "user_behavior.session_count_30d"
for feature in client.find_similar(base, top_k=5, threshold=0.25):
    print(feature.name)
```

The server chooses pgvector similarity when embeddings are available and falls back to TF-IDF otherwise.

## Handle missing features

```python
from featcat_client import FeatureNotFound

try:
    feature = client.get_feature("user_behavior.missing_col")
except FeatureNotFound:
    feature = None
```

Catch `FeatCatError` when you want one handler for network, server, and not-found failures.
