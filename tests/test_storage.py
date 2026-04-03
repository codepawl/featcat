"""Tests for storage backends (local and S3 mock)."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.storage import read_parquet_sample, read_parquet_schema, resolve_parquet_path


class TestLocalStorage:
    def test_resolve_existing_file(self, sample_parquet: Path):
        resolved = resolve_parquet_path(str(sample_parquet))
        assert Path(resolved).exists()

    def test_resolve_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            resolve_parquet_path("/nonexistent/file.parquet")

    def test_resolve_s3_passthrough(self):
        uri = "s3://bucket/path/file.parquet"
        assert resolve_parquet_path(uri) == uri

    def test_read_schema(self, sample_parquet: Path):
        schema = read_parquet_schema(str(sample_parquet))
        field_names = [f.name for f in schema]
        assert "user_id" in field_names
        assert "age" in field_names
        assert "revenue" in field_names
        assert "city" in field_names

    def test_read_schema_types(self, sample_parquet: Path):
        schema = read_parquet_schema(str(sample_parquet))
        type_map = {f.name: str(f.type) for f in schema}
        assert type_map["user_id"] == "int64"
        assert type_map["city"] == "string"

    def test_read_sample_full(self, sample_parquet: Path):
        table = read_parquet_sample(str(sample_parquet))
        assert table.num_rows == 5  # fixture has 5 rows
        assert table.num_columns == 4

    def test_read_sample_limited(self, sample_parquet: Path):
        table = read_parquet_sample(str(sample_parquet), n_rows=3)
        assert table.num_rows == 3

    def test_read_sample_exceeding(self, sample_parquet: Path):
        table = read_parquet_sample(str(sample_parquet), n_rows=100)
        assert table.num_rows == 5  # only 5 rows exist

    def test_read_empty_parquet(self, tmp_path: Path):
        empty_table = pa.table({"a": pa.array([], type=pa.int64())})
        path = tmp_path / "empty.parquet"
        pq.write_table(empty_table, path)

        schema = read_parquet_schema(str(path))
        assert len(schema) == 1

        table = read_parquet_sample(str(path))
        assert table.num_rows == 0


class TestS3Storage:
    def test_s3_schema_attempts_connection(self):
        """S3 reads now attempt real connections (tested separately in test_s3_storage.py)."""
        with pytest.raises((OSError, Exception)):
            read_parquet_schema("s3://bucket/file.parquet")

    def test_s3_sample_attempts_connection(self):
        """S3 reads now attempt real connections (tested separately in test_s3_storage.py)."""
        with pytest.raises((OSError, Exception)):
            read_parquet_sample("s3://bucket/file.parquet")
