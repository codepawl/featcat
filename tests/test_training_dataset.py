"""Service-level tests for local training dataset validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.models import DataSource
from featcat.catalog.training_dataset import build_training_dataset

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def local_parquet_paths(tmp_path: Path) -> tuple[Path, Path]:
    entity_path = tmp_path / "entities.parquet"
    entity = pa.table(
        {
            "user_id": pa.array([1, 2, 3]),
            "event_ts": pa.array(["2026-01-01", "2026-01-02", "2026-01-03"]),
        }
    )
    pq.write_table(entity, entity_path)

    source_path = tmp_path / "features.parquet"
    source = pa.table(
        {
            "user_id": pa.array([1, 2, 3]),
            "event_ts": pa.array(["2026-01-01", "2026-01-02", "2026-01-03"]),
            "score": pa.array([0.1, 0.2, 0.3]),
            "country": pa.array(["US", "CA", "GB"]),
        }
    )
    pq.write_table(source, source_path)
    return entity_path, source_path


def _codes(result) -> set[str]:
    return {error.code for error in result.errors}


def _source(path: Path, *, entity_key: str | None = "user_id", event_ts: str | None = "event_ts") -> DataSource:
    return DataSource(
        name="features",
        path=str(path),
        entity_key=entity_key,
        event_timestamp_column=event_ts,
    )


def test_valid_local_parquet_entity_and_source_pass_validation(local_parquet_paths: tuple[Path, Path]) -> None:
    entity_path, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score", "country"],
        data_source=_source(source_path),
    )

    assert result.is_valid is True
    assert result.errors == []
    assert result.source_path == str(source_path)
    assert result.entity_key == "user_id"
    assert result.entity_timestamp_column == "event_ts"
    assert result.source_event_timestamp_column == "event_ts"


def test_missing_entity_dataframe_file_returns_clear_error(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    _, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(tmp_path / "missing_entities.parquet"),
        feature_columns=["score"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "missing_entity_dataframe" in _codes(result)


def test_missing_source_file_returns_clear_error(local_parquet_paths: tuple[Path, Path], tmp_path: Path) -> None:
    entity_path, _ = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        source_path=str(tmp_path / "missing_source.parquet"),
        entity_key="user_id",
        source_event_timestamp_column="event_ts",
        feature_columns=["score"],
    )

    assert result.is_valid is False
    assert "missing_source_dataframe" in _codes(result)


def test_missing_entity_key_metadata_returns_clear_error(local_parquet_paths: tuple[Path, Path]) -> None:
    entity_path, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path, entity_key=None),
    )

    assert result.is_valid is False
    assert "missing_entity_key_metadata" in _codes(result)


def test_missing_event_timestamp_column_metadata_returns_clear_error(local_parquet_paths: tuple[Path, Path]) -> None:
    entity_path, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path, event_ts=None),
    )

    assert result.is_valid is False
    assert "missing_event_timestamp_column_metadata" in _codes(result)


def test_entity_dataframe_missing_entity_key_returns_clear_error(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    _, source_path = local_parquet_paths
    entity_path = tmp_path / "entities_without_key.parquet"
    pq.write_table(pa.table({"event_ts": pa.array(["2026-01-01"])}), entity_path)

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "entity_dataframe_missing_entity_key" in _codes(result)


def test_entity_dataframe_missing_timestamp_returns_clear_error(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    _, source_path = local_parquet_paths
    entity_path = tmp_path / "entities_without_timestamp.parquet"
    pq.write_table(pa.table({"user_id": pa.array([1])}), entity_path)

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "entity_dataframe_missing_timestamp" in _codes(result)


def test_source_dataframe_missing_entity_key_returns_clear_error(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    entity_path, _ = local_parquet_paths
    source_path = tmp_path / "source_without_key.parquet"
    pq.write_table(pa.table({"event_ts": pa.array(["2026-01-01"]), "score": pa.array([0.1])}), source_path)

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "source_dataframe_missing_entity_key" in _codes(result)


def test_source_dataframe_missing_source_event_timestamp_returns_clear_error(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    entity_path, _ = local_parquet_paths
    source_path = tmp_path / "source_without_event_ts.parquet"
    pq.write_table(pa.table({"user_id": pa.array([1]), "score": pa.array([0.1])}), source_path)

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "source_dataframe_missing_event_timestamp" in _codes(result)


def test_requested_feature_column_missing_returns_clear_error(local_parquet_paths: tuple[Path, Path]) -> None:
    entity_path, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score", "missing_feature"],
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "requested_feature_columns_missing" in _codes(result)
