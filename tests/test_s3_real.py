"""Opt-in integration tests against a real S3 / MinIO endpoint.

Gated on ``@pytest.mark.s3_real`` — excluded from the default ``make test``
run via ``pyproject.toml``'s ``-m "not s3_real"`` addopt. Opt in with::

    FEATCAT_S3_TEST_ENDPOINT=https://s3.amazonaws.com \\
    FEATCAT_S3_TEST_ACCESS_KEY=... \\
    FEATCAT_S3_TEST_SECRET_KEY=... \\
    FEATCAT_S3_TEST_BUCKET=my-test-bucket \\
        pytest -m s3_real

Without those env vars, the ``real_s3_backend`` fixture skips every test
in this module with a clear message naming which vars are missing.

These tests assume the bucket already has fixture data at
``${BUCKET}/featcat-fixtures/`` — see admin-guide for the upload script.
"""

from __future__ import annotations

import pyarrow as pa
import pytest


@pytest.mark.s3_real
@pytest.mark.timeout(120)
def test_real_s3_schema_read(real_s3_env):
    """Schema read against a known fixture parquet at the real endpoint.

    The fixture (``featcat-fixtures/sample.parquet``) must exist in the
    bucket — see admin-guide for the upload procedure. We only validate
    that *some* schema comes back with at least one field, since the
    contents of the fixture aren't pinned by this test.
    """
    from featcat.catalog.storage import _s3_read_schema

    uri = f"s3://{real_s3_env.bucket}/featcat-fixtures/sample.parquet"
    schema = _s3_read_schema(uri)
    assert isinstance(schema, pa.Schema)
    assert len(schema) > 0


@pytest.mark.s3_real
@pytest.mark.timeout(120)
def test_real_s3_discovery_recursive(real_s3_env):
    """Recursive discovery against the real endpoint surfaces fixture parquets.

    Expects at least one parquet under ``featcat-fixtures/``; doesn't pin
    a count because the fixture set may evolve.
    """
    from featcat.catalog.scanner import discover_parquet_files

    uri = f"s3://{real_s3_env.bucket}/featcat-fixtures"
    files = discover_parquet_files(uri, recursive=True)
    assert len(files) >= 1
    assert all(p.startswith(f"s3://{real_s3_env.bucket}/featcat-fixtures/") for p in files)
    assert all(p.endswith(".parquet") for p in files)


@pytest.mark.s3_real
@pytest.mark.timeout(120)
def test_real_s3_bad_credentials_raises(real_s3_backend, monkeypatch: pytest.MonkeyPatch):
    """Wrong creds against the real endpoint surface as OSError.

    Doesn't use ``real_s3_env`` because we override the keys ourselves.
    """
    from featcat.catalog.scanner import discover_parquet_files

    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", real_s3_backend.endpoint_url)
    monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "definitely-wrong")
    monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "also-wrong")
    monkeypatch.setenv("FEATCAT_S3_REGION", "us-east-1")
    monkeypatch.delenv("FEATCAT_S3_SESSION_TOKEN", raising=False)

    with pytest.raises((OSError, FileNotFoundError)):
        discover_parquet_files(f"s3://{real_s3_backend.bucket}/featcat-fixtures", recursive=False)


@pytest.mark.s3_real
@pytest.mark.timeout(120)
def test_real_s3_unreachable_endpoint_times_out(monkeypatch: pytest.MonkeyPatch):
    """A bogus endpoint surfaces an OSError within the configured timeout.

    Skips ``real_s3_env`` deliberately — we want to use a localhost-rejection
    endpoint, not the actual one. The test only verifies that the timeout
    is honored (no indefinite hang); the precise wall-clock bound is set
    by the test marker.
    """
    from featcat.catalog.scanner import discover_parquet_files

    # 127.0.0.1:1 (port 1) consistently rejects on any host.
    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "x")
    monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "x")
    # Short timeouts so the test isn't slow.
    monkeypatch.setenv("FEATCAT_S3_CONNECT_TIMEOUT_MS", "2000")
    monkeypatch.setenv("FEATCAT_S3_REQUEST_TIMEOUT_MS", "2000")

    with pytest.raises(OSError):
        discover_parquet_files("s3://any-bucket/any-prefix", recursive=False)
