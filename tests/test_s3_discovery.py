"""Tests for ``discover_parquet_files`` against S3 prefixes.

End-to-end tests use the MinIO testcontainer fixture (see ``conftest.py``)
and are gated on ``@pytest.mark.s3`` so they skip cleanly when Docker is
absent. Pure-validation tests for the URI parser run in the default suite.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from featcat.catalog.scanner import discover_parquet_files
from featcat.catalog.storage import is_s3_uri, parse_s3_uri

# ---------------------------------------------------------------------------
# End-to-end (require Docker)
# ---------------------------------------------------------------------------


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_s3_enumeration(minio_env):
    """bucket prefix → list of s3:// parquet paths; recursive controls walk."""
    table = pa.table({"x": [1, 2, 3]})
    minio_env.upload_parquet("flat/a.parquet", table)
    minio_env.upload_parquet("flat/b.parquet", table)
    minio_env.upload_parquet("flat/nested/c.parquet", table)

    uri = f"s3://{minio_env.bucket}/flat"

    flat = discover_parquet_files(uri, recursive=False)
    assert len(flat) == 2
    assert all(p.startswith(f"s3://{minio_env.bucket}/flat/") for p in flat)
    assert all(p.endswith(".parquet") for p in flat)

    deep = discover_parquet_files(uri, recursive=True)
    assert len(deep) == 3
    assert f"s3://{minio_env.bucket}/flat/nested/c.parquet" in deep


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_empty_prefix(minio_env):
    """No parquet files under the prefix → empty list, not an error."""
    # Upload a non-parquet file so the prefix exists.
    minio_env.client.put_object(Bucket=minio_env.bucket, Key="empty/readme.txt", Body=b"hi")
    files = discover_parquet_files(f"s3://{minio_env.bucket}/empty", recursive=True)
    assert files == []


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_mixed_files(minio_env):
    """Mixed parquet + csv + json under prefix → only parquet returned."""
    table = pa.table({"x": [1, 2]})
    minio_env.upload_parquet("mixed/a.parquet", table)
    minio_env.client.put_object(Bucket=minio_env.bucket, Key="mixed/b.csv", Body=b"x,y\n1,2\n")
    minio_env.client.put_object(Bucket=minio_env.bucket, Key="mixed/c.json", Body=b'{"x":1}')

    files = discover_parquet_files(f"s3://{minio_env.bucket}/mixed", recursive=True)
    assert len(files) == 1
    assert files[0].endswith("/a.parquet")


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_recursive_vs_flat(minio_env):
    """recursive=False stops at the first level; recursive=True walks all."""
    table = pa.table({"x": [1]})
    minio_env.upload_parquet("root/top.parquet", table)
    minio_env.upload_parquet("root/sub/mid.parquet", table)
    minio_env.upload_parquet("root/sub/sub2/leaf.parquet", table)

    uri = f"s3://{minio_env.bucket}/root"
    assert len(discover_parquet_files(uri, recursive=False)) == 1
    assert len(discover_parquet_files(uri, recursive=True)) == 3


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_missing_prefix_raises(minio_env):
    """Non-existent prefix surfaces as FileNotFoundError with the original URI."""
    uri = f"s3://{minio_env.bucket}/does-not-exist"
    with pytest.raises(FileNotFoundError, match="does-not-exist"):
        discover_parquet_files(uri, recursive=True)


# ---------------------------------------------------------------------------
# Pure URI-parsing tests (no Docker required)
# ---------------------------------------------------------------------------


class TestS3UriParsing:
    def test_is_s3_uri_positive(self):
        assert is_s3_uri("s3://bucket/key")
        assert is_s3_uri("s3://b/")
        assert is_s3_uri("s3://")  # still has the scheme; parse_s3_uri catches malformed

    def test_is_s3_uri_negative(self):
        assert not is_s3_uri("/local/path")
        assert not is_s3_uri("file:///x")
        assert not is_s3_uri("http://example.com/x.parquet")
        assert not is_s3_uri("s3:/missing-slash")
        assert not is_s3_uri("")

    def test_parse_s3_uri_with_prefix(self):
        assert parse_s3_uri("s3://bucket/key/path") == ("bucket", "key/path")

    def test_parse_s3_uri_bucket_only(self):
        assert parse_s3_uri("s3://bucket") == ("bucket", "")

    def test_parse_s3_uri_trailing_slash_keeps_empty_prefix(self):
        # "s3://bucket/" splits to ("bucket", "") — the trailing slash is dropped
        # by the split(..., 1) since prefix becomes the empty string after the slash.
        assert parse_s3_uri("s3://bucket/") == ("bucket", "")

    def test_parse_s3_uri_empty_bucket(self):
        with pytest.raises(ValueError, match="empty bucket"):
            parse_s3_uri("s3:///key")

    def test_parse_s3_uri_empty_after_scheme(self):
        with pytest.raises(ValueError, match="empty bucket"):
            parse_s3_uri("s3://")

    def test_parse_s3_uri_not_s3(self):
        with pytest.raises(ValueError, match="not an S3 URI"):
            parse_s3_uri("/local/path")


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_discover_parquet_files_malformed_uri(minio_env):
    """Malformed s3:// URIs raise ValueError before any network call."""
    with pytest.raises(ValueError, match="empty bucket"):
        discover_parquet_files("s3://", recursive=False)
    with pytest.raises(ValueError, match="empty bucket"):
        discover_parquet_files("s3:///orphan-key", recursive=False)
