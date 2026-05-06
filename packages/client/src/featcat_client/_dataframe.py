"""DataFrame helpers — parquet reads and group joins.

Kept separate from ``models.py`` so importing models doesn't pull in pyarrow /
polars at import time. Lazy imports inside helpers keep the dependency graph
shallow for callers that only want metadata.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    import polars as pl

    from .models import DataSource, Feature, FeatureGroupDetail


@lru_cache(maxsize=64)
def _read_parquet_cached(path: str) -> pl.DataFrame:
    """Read a parquet file once per process. ``lru_cache`` keys on path."""
    import polars as pl

    # ``pl.read_parquet`` handles local + s3:// URIs natively. For plain http(s)
    # URLs we'd need s3fs/fsspec, but those aren't in featcat's data path today.
    return pl.read_parquet(path)


def read_feature_parquet(feature: Feature, source: DataSource) -> pl.DataFrame:
    """Return a 1-column polars DataFrame for ``feature.column_name``."""
    df = _read_parquet_cached(source.path)
    if feature.column_name not in df.columns:
        msg = f"Column {feature.column_name!r} not found in source parquet at {source.path}"
        raise KeyError(msg)
    return df.select(feature.column_name)


def group_to_polars(
    detail: FeatureGroupDetail,
    *,
    entity_key: str | None,
    source_resolver: Callable[[str], DataSource] | None,
) -> pl.DataFrame:
    """Join all member features on ``entity_key`` into one polars DataFrame.

    Algorithm:
    1. For each member feature, resolve its source via ``source_resolver``.
    2. Read the source parquet once (cached across members from same source).
    3. Auto-detect entity_key when omitted: pick the column that's present in
       every member's parquet AND has the same dtype (commonly ``user_id`` /
       ``session_id`` / etc. in the data team's pipelines). Raise on ambiguity.
    4. Inner-join all per-source frames on the entity key.
    """
    if not detail.members:
        import polars as pl

        return pl.DataFrame()

    if source_resolver is None:
        msg = "source_resolver is required to read group data — pass via FeatCatClient.get_group()"
        raise ValueError(msg)

    # Group members by source so we read each parquet once.
    members_by_source: dict[str, list[Feature]] = {}
    for f in detail.members:
        members_by_source.setdefault(f.data_source_id, []).append(f)

    # Build per-source DataFrames containing the entity key + needed columns.
    per_source_frames: list[Any] = []  # list[pl.DataFrame]
    candidate_keys: list[set[str]] = []
    for sid, feats in members_by_source.items():
        source = source_resolver(sid)
        full = _read_parquet_cached(source.path)
        candidate_keys.append(set(full.columns) - {f.column_name for f in feats})
        per_source_frames.append((full, [f.column_name for f in feats]))

    if entity_key is None:
        common = set.intersection(*candidate_keys) if candidate_keys else set()
        if not common:
            msg = (
                "Cannot auto-detect entity_key: no column is shared across all member parquet files. "
                "Pass entity_key=... explicitly."
            )
            raise ValueError(msg)
        if len(common) > 1:
            # Prefer common ID column names; otherwise the caller must disambiguate.
            preferred = ["user_id", "session_id", "id", "entity_id", "device_id"]
            for p in preferred:
                if p in common:
                    entity_key = p
                    break
            else:
                msg = (
                    f"Multiple shared columns found across member parquets: {sorted(common)}. "
                    "Pass entity_key=... explicitly."
                )
                raise ValueError(msg)
        else:
            entity_key = next(iter(common))

    import polars as pl

    result: pl.DataFrame | None = None
    for full, cols in per_source_frames:
        if entity_key not in full.columns:
            msg = f"entity_key={entity_key!r} not present in source parquet"
            raise KeyError(msg)
        slim = full.select([entity_key, *cols])
        result = slim if result is None else result.join(slim, on=entity_key, how="inner")
    assert result is not None  # guarded by `if not detail.members` above  # noqa: S101
    return result
