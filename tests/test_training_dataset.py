"""Service-level tests for local training dataset validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog import storage, training_dataset
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


def _write_table(path: Path, data: dict) -> Path:
    pq.write_table(pa.table(data), path)
    return path


def _pit_result(tmp_path: Path, entity_data: dict, source_data: dict, feature_columns: list[str] | None = None):
    entity_path = _write_table(tmp_path / "pit_entities.parquet", entity_data)
    source_path = _write_table(tmp_path / "pit_source.parquet", source_data)
    return build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=feature_columns or ["score"],
        data_source=_source(source_path),
    )


def test_point_in_time_join_exact_timestamp_match(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"])},
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"]), "score": pa.array([20])},
    )

    assert result.is_valid is True
    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [20]


def test_point_in_time_join_latest_prior_timestamp_is_selected(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-05"])},
        {
            "user_id": pa.array([1, 1]),
            "event_ts": pa.array(["2026-01-01", "2026-01-04"]),
            "score": pa.array([10, 40]),
        },
    )

    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [40]


def test_point_in_time_join_future_values_do_not_leak(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-03"])},
        {
            "user_id": pa.array([1, 1]),
            "event_ts": pa.array(["2026-01-01", "2026-01-04"]),
            "score": pa.array([10, 999]),
        },
    )

    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [10]


def test_point_in_time_join_multiple_source_rows_select_latest_eligible_row(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-10"])},
        {
            "user_id": pa.array([1, 1, 1]),
            "event_ts": pa.array(["2026-01-01", "2026-01-09", "2026-01-11"]),
            "score": pa.array([10, 90, 110]),
        },
    )

    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [90]


def test_point_in_time_join_multiple_entities_are_isolated(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1, 2]), "event_ts": pa.array(["2026-01-05", "2026-01-05"])},
        {
            "user_id": pa.array([1, 2, 2]),
            "event_ts": pa.array(["2026-01-04", "2026-01-01", "2026-01-04"]),
            "score": pa.array([100, 200, 240]),
        },
    )

    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [100, 240]


def test_point_in_time_join_preserves_entity_row_order(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {
            "user_id": pa.array([2, 1, 2]),
            "event_ts": pa.array(["2026-01-05", "2026-01-03", "2026-01-02"]),
            "label": pa.array([0, 1, 0]),
        },
        {
            "user_id": pa.array([1, 2, 2]),
            "event_ts": pa.array(["2026-01-01", "2026-01-01", "2026-01-04"]),
            "score": pa.array([10, 20, 40]),
        },
    )

    assert result.dataframe is not None
    assert result.dataframe["user_id"].to_list() == [2, 1, 2]
    assert result.dataframe["score"].to_list() == [40, 10, 20]


def test_point_in_time_join_does_not_leak_internal_row_index_column(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {
            "user_id": pa.array([1]),
            "event_ts": pa.array(["2026-01-03"]),
            "__featcat_entity_row": pa.array(["entity value"]),
        },
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"]), "score": pa.array([20])},
    )

    assert result.dataframe is not None
    assert "__featcat_entity_row_1" not in result.dataframe.columns
    assert result.dataframe.columns == ["user_id", "event_ts", "__featcat_entity_row", "score"]


def test_point_in_time_join_feature_entity_column_collision_returns_validation_error(tmp_path: Path) -> None:
    entity_path = _write_table(
        tmp_path / "entities.parquet",
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-03"]), "score": pa.array([111])},
    )
    source_path = _write_table(
        tmp_path / "source.parquet",
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"]), "score": pa.array([222])},
    )
    output_path = tmp_path / "collision.parquet"

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        output_path=str(output_path),
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert "feature_column_collides_with_entity_dataframe" in _codes(result)
    assert result.dataframe is None
    assert not output_path.exists()


def test_point_in_time_join_no_historical_match_returns_null_feature_value(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-01"])},
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"]), "score": pa.array([20])},
    )

    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [None]
    assert result.unresolved_row_count == 1
    assert result.missing_feature_value_count == 1


def test_point_in_time_join_requested_multiple_feature_columns_are_joined(tmp_path: Path) -> None:
    result = _pit_result(
        tmp_path,
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-03"])},
        {
            "user_id": pa.array([1]),
            "event_ts": pa.array(["2026-01-02"]),
            "score": pa.array([20]),
            "country": pa.array(["US"]),
        },
        ["score", "country"],
    )

    assert result.dataframe is not None
    assert result.feature_count == 2
    assert result.dataframe.select(["score", "country"]).to_dicts() == [{"score": 20, "country": "US"}]


def test_point_in_time_join_output_path_writes_local_parquet(tmp_path: Path) -> None:
    entity_path = _write_table(
        tmp_path / "entities.parquet",
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-03"])},
    )
    source_path = _write_table(
        tmp_path / "source.parquet",
        {"user_id": pa.array([1]), "event_ts": pa.array(["2026-01-02"]), "score": pa.array([20])},
    )
    output_path = tmp_path / "dataset.parquet"

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        output_path=str(output_path),
        data_source=_source(source_path),
    )

    assert result.is_valid is True
    assert result.output_path == str(output_path)
    assert output_path.exists()
    assert pq.read_table(output_path).to_pydict()["score"] == [20]


def test_point_in_time_join_validation_errors_prevent_output_writing(
    local_parquet_paths: tuple[Path, Path], tmp_path: Path
) -> None:
    entity_path, source_path = local_parquet_paths
    output_path = tmp_path / "should_not_exist.parquet"

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["missing_feature"],
        output_path=str(output_path),
        data_source=_source(source_path),
    )

    assert result.is_valid is False
    assert result.dataframe is None
    assert result.output_path is None
    assert not output_path.exists()


def test_s3_paths_are_accepted_with_config_and_mocked_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    import polars as pl

    entity_path = "s3://featcat/entities.parquet"
    source_path = "s3://featcat/features.parquet"
    output_path = "s3://featcat/training.parquet"
    captured: dict[str, object] = {}

    monkeypatch.setattr(training_dataset, "s3_config_missing_fields", lambda: [])
    monkeypatch.setattr(
        training_dataset,
        "_parquet_columns",
        lambda path: {"user_id", "event_ts"} if path == entity_path else {"user_id", "event_ts", "score", "country"},
    )

    def fake_build_point_in_time_frame(**kwargs):
        captured["build_kwargs"] = kwargs
        return pl.DataFrame({"user_id": [1], "event_ts": ["2026-01-01"], "score": [10], "country": ["US"]})

    def fake_write_parquet_frame(frame: pl.DataFrame, path: str) -> None:
        captured["output_path"] = path
        captured["written_columns"] = frame.columns

    monkeypatch.setattr(training_dataset, "_build_point_in_time_frame", fake_build_point_in_time_frame)
    monkeypatch.setattr(training_dataset, "_write_parquet_frame", fake_write_parquet_frame)

    result = build_training_dataset(
        entity_df_path=entity_path,
        source_path=source_path,
        entity_key="user_id",
        entity_timestamp_column="event_ts",
        source_event_timestamp_column="event_ts",
        feature_columns=["score", "country"],
        output_path=output_path,
    )

    assert result.is_valid is True
    assert result.output_path == output_path
    assert captured["output_path"] == output_path
    assert captured["build_kwargs"] == {
        "entity_df_path": entity_path,
        "source_path": source_path,
        "entity_key": "user_id",
        "entity_timestamp_column": "event_ts",
        "source_event_timestamp_column": "event_ts",
        "feature_columns": ["score", "country"],
    }


def test_s3_missing_config_returns_structured_error(
    local_parquet_paths: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source_path = local_parquet_paths

    monkeypatch.setattr(
        training_dataset,
        "s3_config_missing_fields",
        lambda: ["FEATCAT_S3_ENDPOINT_URL", "FEATCAT_S3_ACCESS_KEY_ID", "FEATCAT_S3_SECRET_ACCESS_KEY"],
    )

    result = build_training_dataset(
        entity_df_path="s3://featcat/entities.parquet",
        source_path=str(source_path),
        entity_key="user_id",
        entity_timestamp_column="event_ts",
        source_event_timestamp_column="event_ts",
        feature_columns=["score"],
    )

    assert result.is_valid is False
    assert "missing_s3_config" in _codes(result)
    assert result.errors[0].field == "entity_df_path"


def test_unsupported_remote_scheme_returns_clear_error(local_parquet_paths: tuple[Path, Path]) -> None:
    _, source_path = local_parquet_paths

    result = build_training_dataset(
        entity_df_path="gs://featcat/entities.parquet",
        source_path=str(source_path),
        entity_key="user_id",
        entity_timestamp_column="event_ts",
        source_event_timestamp_column="event_ts",
        feature_columns=["score"],
    )

    assert result.is_valid is False
    assert "unsupported_entity_path_scheme" in _codes(result)
    assert result.errors[0].message.startswith("Unsupported entity dataframe path scheme: gs")


def test_s3_filesystem_uses_configured_backend_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeS3FileSystem:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY_ID", "minio")
    monkeypatch.setenv("FEATCAT_S3_SECRET_ACCESS_KEY", "minio-secret")
    monkeypatch.setenv("FEATCAT_S3_REGION", "us-east-1")
    monkeypatch.setenv("FEATCAT_S3_FORCE_PATH_STYLE", "true")
    monkeypatch.delenv("FEATCAT_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("FEATCAT_S3_SECRET_KEY", raising=False)
    monkeypatch.setattr(storage, "S3FileSystem", FakeS3FileSystem)

    storage._get_s3_filesystem()

    assert captured["endpoint_override"] == "127.0.0.1:9000"
    assert captured["scheme"] == "http"
    assert captured["access_key"] == "minio"
    assert captured["secret_key"] == "minio-secret"
    assert captured["region"] == "us-east-1"
    assert captured["force_virtual_addressing"] is False
