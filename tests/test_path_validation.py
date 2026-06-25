"""Tests for ``validate_path_input`` and its wiring into the FastAPI routes.

Closes audit gap #6 (API-boundary validation). The validator runs at the
HTTP edge so malformed paths never reach the storage layer; the route
returns ``422 Unprocessable Entity`` with a clear message instead of a
generic 500 from a downstream traceback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.storage import validate_path_input

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Pure-Python validator tests
# ---------------------------------------------------------------------------


class TestValidatePathInputAccepts:
    def test_absolute_local(self):
        assert validate_path_input("/tmp/data.parquet") == "/tmp/data.parquet"

    def test_absolute_local_with_spaces_trimmed(self):
        assert validate_path_input("  /tmp/data.parquet  ") == "/tmp/data.parquet"

    def test_s3_with_prefix(self):
        assert validate_path_input("s3://bucket/key/file.parquet") == "s3://bucket/key/file.parquet"

    def test_s3_bucket_only(self):
        assert validate_path_input("s3://bucket") == "s3://bucket"

    def test_s3_trailing_slash(self):
        assert validate_path_input("s3://bucket/") == "s3://bucket/"


class TestValidatePathInputRejects:
    def test_empty(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_path_input("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="must not be empty"):
            validate_path_input("   \t  ")

    def test_relative_local(self):
        with pytest.raises(ValueError, match="must be absolute"):
            validate_path_input("data/foo.parquet")

    def test_relative_dot(self):
        with pytest.raises(ValueError, match="must be absolute"):
            validate_path_input("./foo.parquet")

    def test_relative_dotdot(self):
        with pytest.raises(ValueError, match="must be absolute"):
            validate_path_input("../foo.parquet")

    def test_unsupported_scheme_http(self):
        with pytest.raises(ValueError, match="unsupported URI scheme"):
            validate_path_input("http://example.com/x.parquet")

    def test_unsupported_scheme_file(self):
        with pytest.raises(ValueError, match="unsupported URI scheme"):
            validate_path_input("file:///x.parquet")

    def test_unsupported_scheme_gs(self):
        with pytest.raises(ValueError, match="unsupported URI scheme"):
            validate_path_input("gs://bucket/x.parquet")

    def test_malformed_s3_empty_bucket(self):
        with pytest.raises(ValueError, match="empty bucket"):
            validate_path_input("s3://")

    def test_malformed_s3_no_bucket_with_key(self):
        with pytest.raises(ValueError, match="empty bucket"):
            validate_path_input("s3:///key")

    def test_control_chars_rejected(self):
        with pytest.raises(ValueError, match="control characters"):
            validate_path_input("/tmp/foo\x00bar.parquet")

    def test_newline_rejected(self):
        with pytest.raises(ValueError, match="control characters"):
            validate_path_input("/tmp/foo\nbar.parquet")

    def test_non_string_rejected(self):
        with pytest.raises(ValueError, match="must be a string"):
            validate_path_input(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# API endpoint 422 tests — make sure validator is wired correctly
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client(tmp_path: Path):
    """A TestClient with a temporary catalog."""
    from featcat.catalog.local import LocalBackend
    from featcat.server import create_app
    from featcat.server.deps import get_db

    db = LocalBackend(str(tmp_path / "api-validation.db"))
    db.init_db()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestScanBulkValidation:
    def test_empty_path_returns_422(self, api_client):
        r = api_client.post("/api/scan-bulk", json={"path": "", "recursive": False})
        assert r.status_code == 422
        assert "empty" in r.json()["detail"].lower()

    def test_relative_path_returns_422(self, api_client):
        r = api_client.post("/api/scan-bulk", json={"path": "relative/dir"})
        assert r.status_code == 422
        assert "absolute" in r.json()["detail"].lower()

    def test_unsupported_scheme_returns_422(self, api_client):
        r = api_client.post("/api/scan-bulk", json={"path": "http://example.com/x"})
        assert r.status_code == 422
        assert "scheme" in r.json()["detail"].lower()

    def test_malformed_s3_returns_422(self, api_client):
        r = api_client.post("/api/scan-bulk", json={"path": "s3://"})
        assert r.status_code == 422
        assert "bucket" in r.json()["detail"].lower()

    def test_control_chars_returns_422(self, api_client):
        r = api_client.post("/api/scan-bulk", json={"path": "/tmp/foo\x00bar"})
        assert r.status_code == 422
        assert "control" in r.json()["detail"].lower()

    def test_scan_failure_does_not_register_empty_source(self, api_client, tmp_path: Path, monkeypatch):
        data_dir = tmp_path / "bulk"
        data_dir.mkdir()
        bad_file = data_dir / "bad.parquet"
        bad_file.write_text("not parquet")

        def _raise(_path: str):
            raise RuntimeError("bad parquet")

        monkeypatch.setattr("featcat.server.routes.scan.scan_source", _raise)

        r = api_client.post("/api/scan-bulk", json={"path": str(data_dir), "recursive": False})

        assert r.status_code == 200
        assert r.json()["details"][0]["status"] == "error"
        assert api_client.get("/api/sources").json() == []


class TestSourcesValidation:
    def test_empty_path_returns_422(self, api_client):
        r = api_client.post("/api/sources", json={"name": "x", "path": ""})
        assert r.status_code == 422
        assert "empty" in r.json()["detail"].lower()

    def test_relative_path_returns_422(self, api_client):
        r = api_client.post("/api/sources", json={"name": "x", "path": "relative/x.parquet"})
        assert r.status_code == 422

    def test_unsupported_scheme_returns_422(self, api_client):
        r = api_client.post("/api/sources", json={"name": "x", "path": "file:///x.parquet"})
        assert r.status_code == 422

    def test_storage_type_mismatch_returns_422(self, api_client, tmp_path: Path):
        """The DataSource validator rejects storage_type that disagrees with the
        URI scheme. The route surfaces that as 422 (Phase 5.3)."""
        # Use an actual local path so validate_path_input passes (it doesn't
        # check existence). The DataSource validator should then catch the
        # storage_type=s3 / local-path mismatch.
        local_path = str(tmp_path / "x.parquet")
        r = api_client.post(
            "/api/sources",
            json={"name": "x", "path": local_path, "storage_type": "s3"},
        )
        assert r.status_code == 422
        assert "storage_type" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DataSource model-level enforcement tests
# ---------------------------------------------------------------------------


class TestDataSourceStorageType:
    def test_auto_derives_local(self):
        from featcat.catalog.models import DataSource

        s = DataSource(name="x", path="/tmp/x.parquet")
        assert s.storage_type == "local"

    def test_auto_derives_s3(self):
        from featcat.catalog.models import DataSource

        s = DataSource(name="x", path="s3://bucket/x.parquet")
        assert s.storage_type == "s3"

    def test_explicit_local_with_local_path(self):
        from featcat.catalog.models import DataSource

        s = DataSource(name="x", path="/tmp/x.parquet", storage_type="local")
        assert s.storage_type == "local"

    def test_explicit_s3_with_s3_path(self):
        from featcat.catalog.models import DataSource

        s = DataSource(name="x", path="s3://b/x.parquet", storage_type="s3")
        assert s.storage_type == "s3"

    def test_mismatch_s3_path_local_type_raises(self):
        from pydantic import ValidationError

        from featcat.catalog.models import DataSource

        with pytest.raises(ValidationError, match="does not match path scheme"):
            DataSource(name="x", path="s3://b/x.parquet", storage_type="local")

    def test_mismatch_local_path_s3_type_raises(self):
        from pydantic import ValidationError

        from featcat.catalog.models import DataSource

        with pytest.raises(ValidationError, match="does not match path scheme"):
            DataSource(name="x", path="/tmp/x.parquet", storage_type="s3")
