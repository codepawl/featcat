"""Tests for the S3 storage backend.

End-to-end tests gated on ``@pytest.mark.s3`` use the MinIO testcontainer
fixture (see ``conftest.py``). Pure-Python config tests don't need MinIO
and run as part of the default suite.

Replaces a prior moto-based fixture that couldn't intercept PyArrow's
C++-backed S3 client. MinIO via testcontainers is a real S3-compatible
endpoint that PyArrow speaks to natively.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

BUCKET = "test-bucket"  # legacy name kept for the pure-config tests below


# ---------------------------------------------------------------------------
# End-to-end S3 read tests (require Docker)
# ---------------------------------------------------------------------------


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_read_s3_schema(minio_env):
    """PyArrow S3FileSystem reads a parquet schema from MinIO."""
    from featcat.catalog.storage import _s3_read_schema

    table = pa.table(
        {
            "user_id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "score": pa.array([0.5, 0.8, 0.3, 0.9, 0.1], type=pa.float64()),
            "city": pa.array(["HCM", "HN", "DN", "HCM", None], type=pa.string()),
        }
    )
    uri = minio_env.upload_parquet("features/test.parquet", table)

    schema = _s3_read_schema(uri)
    field_names = [f.name for f in schema]
    assert set(field_names) == {"user_id", "score", "city"}


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_scan_s3_source(minio_env):
    """``scan_source`` returns column info for a parquet sitting in S3."""
    from featcat.catalog.scanner import scan_source

    table = pa.table(
        {
            "user_id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "score": pa.array([0.5, 0.8, 0.3, 0.9, 0.1], type=pa.float64()),
            "city": pa.array(["HCM", "HN", "DN", "HCM", None], type=pa.string()),
        }
    )
    uri = minio_env.upload_parquet("features/scan.parquet", table)

    columns = scan_source(uri)
    assert len(columns) == 3
    names = {c.column_name for c in columns}
    assert names == {"user_id", "score", "city"}


# ---------------------------------------------------------------------------
# Pure-Python helpers (no Docker required)
# ---------------------------------------------------------------------------


def test_resolve_s3_path():
    """``resolve_parquet_path`` passes S3 URIs through unchanged."""
    from featcat.catalog.storage import resolve_parquet_path

    uri = f"s3://{BUCKET}/some/key.parquet"
    assert resolve_parquet_path(uri) == uri


def test_s3_uri_to_path():
    """``_s3_uri_to_path`` strips only the ``s3://`` scheme, nothing else."""
    from featcat.catalog.storage import _s3_uri_to_path

    assert _s3_uri_to_path("s3://bucket/key/file.parquet") == "bucket/key/file.parquet"


# ---------------------------------------------------------------------------
# Config field tests
# ---------------------------------------------------------------------------


class TestS3Config:
    def test_settings_have_s3_fields(self):
        from featcat.config import Settings

        s = Settings()
        assert hasattr(s, "s3_endpoint_url")
        assert hasattr(s, "s3_access_key")
        assert hasattr(s, "s3_secret_key")
        assert hasattr(s, "s3_region")
        assert s.s3_region == "us-east-1"

    def test_s3_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", "http://minio:9000")
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "mykey")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "mysecret")
        monkeypatch.setenv("FEATCAT_S3_REGION", "ap-southeast-1")

        from featcat.config import Settings

        s = Settings()
        assert s.s3_endpoint_url == "http://minio:9000"
        assert s.s3_access_key == "mykey"
        assert s.s3_secret_key == "mysecret"
        assert s.s3_region == "ap-southeast-1"
