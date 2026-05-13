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


@pytest.mark.s3
@pytest.mark.timeout(60)
def test_aws_env_fallback_works(minio_backend, monkeypatch: pytest.MonkeyPatch):
    """When FEATCAT_S3_* creds are unset, PyArrow's default chain reads
    standard ``AWS_*`` env vars. Verifies the fallback works against the
    MinIO testcontainer (using minio_backend directly, NOT minio_env, so
    we control the env state ourselves)."""
    from featcat.catalog.scanner import scan_source

    # Endpoint still needs to come from FEATCAT_S3_ENDPOINT_URL — there's no
    # universally-honored AWS env var for arbitrary S3 endpoints (AWS_ENDPOINT_URL_S3
    # is botocore-2 / very new PyArrow only). We're testing the CREDENTIAL
    # fallback, not endpoint fallback.
    monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", minio_backend.endpoint_url)
    monkeypatch.setenv("FEATCAT_S3_REGION", "us-east-1")
    monkeypatch.delenv("FEATCAT_S3_ACCESS_KEY", raising=False)
    monkeypatch.delenv("FEATCAT_S3_SECRET_KEY", raising=False)
    monkeypatch.delenv("FEATCAT_S3_SESSION_TOKEN", raising=False)
    # Standard AWS env vars — PyArrow's default credential chain picks these up
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", minio_backend.access_key)
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", minio_backend.secret_key)

    table = pa.table({"x": pa.array([1, 2, 3], type=pa.int64())})
    uri = minio_backend.upload_parquet("fallback/test.parquet", table)

    columns = scan_source(uri)
    assert len(columns) == 1
    assert columns[0].column_name == "x"


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
    def test_settings_have_s3_fields(self, monkeypatch: pytest.MonkeyPatch):
        # Clear any inherited test-runner env so defaults are visible.
        for key in (
            "FEATCAT_S3_ACCESS_KEY",
            "FEATCAT_S3_SECRET_KEY",
            "FEATCAT_S3_SESSION_TOKEN",
            "FEATCAT_S3_CONNECT_TIMEOUT_MS",
            "FEATCAT_S3_REQUEST_TIMEOUT_MS",
        ):
            monkeypatch.delenv(key, raising=False)
        from featcat.config import Settings

        s = Settings()
        assert hasattr(s, "s3_endpoint_url")
        assert hasattr(s, "s3_access_key")
        assert hasattr(s, "s3_secret_key")
        assert hasattr(s, "s3_session_token")
        assert hasattr(s, "s3_region")
        assert hasattr(s, "s3_connect_timeout_ms")
        assert hasattr(s, "s3_request_timeout_ms")
        assert s.s3_region == "us-east-1"
        assert s.s3_session_token is None
        assert s.s3_connect_timeout_ms == 10_000
        assert s.s3_request_timeout_ms == 60_000

    def test_s3_env_vars(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ENDPOINT_URL", "http://minio:9000")
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "mykey")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "mysecret")
        monkeypatch.setenv("FEATCAT_S3_REGION", "ap-southeast-1")
        monkeypatch.setenv("FEATCAT_S3_SESSION_TOKEN", "tok-xyz")
        monkeypatch.setenv("FEATCAT_S3_CONNECT_TIMEOUT_MS", "5000")
        monkeypatch.setenv("FEATCAT_S3_REQUEST_TIMEOUT_MS", "30000")

        from featcat.config import Settings

        s = Settings()
        assert s.s3_endpoint_url == "http://minio:9000"
        assert s.s3_access_key == "mykey"
        assert s.s3_secret_key == "mysecret"
        assert s.s3_region == "ap-southeast-1"
        assert s.s3_session_token == "tok-xyz"
        assert s.s3_connect_timeout_ms == 5000
        assert s.s3_request_timeout_ms == 30000


class TestS3PartialConfigValidator:
    """The Settings model_validator must reject single-key configs at load
    time (audit gap #5: silent fallback is broken-by-design)."""

    def test_access_only_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "only-access")
        monkeypatch.delenv("FEATCAT_S3_SECRET_KEY", raising=False)
        from pydantic import ValidationError

        from featcat.config import Settings

        with pytest.raises(ValidationError, match="must be set together"):
            Settings()

    def test_secret_only_raises(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FEATCAT_S3_ACCESS_KEY", raising=False)
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "only-secret")
        from pydantic import ValidationError

        from featcat.config import Settings

        with pytest.raises(ValidationError, match="must be set together"):
            Settings()

    def test_both_set_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "k")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "s")
        from featcat.config import Settings

        Settings()  # no raise

    def test_both_unset_passes(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FEATCAT_S3_ACCESS_KEY", raising=False)
        monkeypatch.delenv("FEATCAT_S3_SECRET_KEY", raising=False)
        from featcat.config import Settings

        Settings()  # default-chain mode; no raise


class TestS3FilesystemKwargs:
    """Mock-the-constructor tests so we can assert exactly which kwargs
    reach PyArrow without standing up an actual S3FileSystem."""

    def test_timeouts_converted_from_ms_to_seconds(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_CONNECT_TIMEOUT_MS", "7500")
        monkeypatch.setenv("FEATCAT_S3_REQUEST_TIMEOUT_MS", "120000")
        # Both creds set so we don't hit the partial-config validator.
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "k")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "s")

        captured: dict = {}

        def fake_fs(**kwargs):
            captured.update(kwargs)
            return object()  # placeholder; storage.py returns it as-is

        monkeypatch.setattr("pyarrow.fs.S3FileSystem", fake_fs)
        from featcat.catalog.storage import _get_s3_filesystem

        _get_s3_filesystem()
        assert captured["connect_timeout"] == 7.5
        assert captured["request_timeout"] == 120.0

    def test_session_token_passed_when_set(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "k")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "s")
        monkeypatch.setenv("FEATCAT_S3_SESSION_TOKEN", "tok-abc")

        captured: dict = {}
        monkeypatch.setattr(
            "pyarrow.fs.S3FileSystem",
            lambda **kw: captured.update(kw) or object(),
        )
        from featcat.catalog.storage import _get_s3_filesystem

        _get_s3_filesystem()
        assert captured.get("session_token") == "tok-abc"

    def test_session_token_omitted_when_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("FEATCAT_S3_ACCESS_KEY", "k")
        monkeypatch.setenv("FEATCAT_S3_SECRET_KEY", "s")
        monkeypatch.delenv("FEATCAT_S3_SESSION_TOKEN", raising=False)

        captured: dict = {}
        monkeypatch.setattr(
            "pyarrow.fs.S3FileSystem",
            lambda **kw: captured.update(kw) or object(),
        )
        from featcat.catalog.storage import _get_s3_filesystem

        _get_s3_filesystem()
        assert "session_token" not in captured

    def test_credentials_omitted_when_both_unset(self, monkeypatch: pytest.MonkeyPatch):
        """No explicit creds → PyArrow's default chain. Region + timeouts
        still passed (deterministic behavior)."""
        monkeypatch.delenv("FEATCAT_S3_ACCESS_KEY", raising=False)
        monkeypatch.delenv("FEATCAT_S3_SECRET_KEY", raising=False)
        monkeypatch.delenv("FEATCAT_S3_SESSION_TOKEN", raising=False)

        captured: dict = {}
        monkeypatch.setattr(
            "pyarrow.fs.S3FileSystem",
            lambda **kw: captured.update(kw) or object(),
        )
        from featcat.catalog.storage import _get_s3_filesystem

        _get_s3_filesystem()
        assert "access_key" not in captured
        assert "secret_key" not in captured
        assert "session_token" not in captured
        assert "region" in captured
        assert "connect_timeout" in captured
