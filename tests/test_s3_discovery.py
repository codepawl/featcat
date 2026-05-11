"""Tests for ``discover_parquet_files`` against S3 prefixes.

The main enumeration test is marked ``xfail(strict=True)`` for Phase 2 because
``discover_parquet_files`` does not yet handle ``s3://`` URIs — Phase 3 wires
the S3 branch and removes the xfail decorator. ``strict=True`` ensures a
premature pass (e.g. the function silently no-ops) surfaces as an XPASS
failure rather than going unnoticed.

When ``Phase 3`` lands, REMOVE the ``@pytest.mark.xfail`` decorator on
``test_discover_parquet_files_s3_enumeration``.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from featcat.catalog.scanner import discover_parquet_files


@pytest.mark.s3
@pytest.mark.timeout(60)
@pytest.mark.xfail(
    strict=True,
    reason="discover_parquet_files S3 branch is wired in Phase 3",
)
def test_discover_parquet_files_s3_enumeration(minio_env):
    """Phase 3 contract: bucket prefix → list of s3:// parquet paths,
    recursive flag controls whether nested keys are walked."""
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
