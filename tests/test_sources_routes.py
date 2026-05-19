"""HTTP-level tests for /api/sources endpoints added alongside the Sources UI.

Pins the contract the React client (``web/src/api.ts`` `api.sources`) and
the RemoteBackend HTTP mirror both depend on. Cascade-delete, impact lookup
and scan-log persistence are exercised via the same TestClient pattern as
``tests/test_server.py`` so failures surface against the real route wiring,
not against a mocked backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from featcat.server.app import build_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def app(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "sources_routes.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    return build_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def parquet_file(tmp_path: Path) -> str:
    """Tiny parquet file the scan endpoints can register against."""
    table = pa.table({"user_id": [1, 2, 3], "amount": [10.5, 20.0, 30.5]})
    path = tmp_path / "sample.parquet"
    pq.write_table(table, path)
    return str(path)


def _add_source(client: TestClient, name: str, path: str) -> dict:
    resp = client.post("/api/sources", json={"name": name, "path": path})
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDeleteSource:
    def test_delete_cascades_features(self, client, parquet_file):
        _add_source(client, "del_src", parquet_file)
        client.post("/api/sources/del_src/scan")
        # Two features registered (user_id, amount).
        feats_before = client.get("/api/features", params={"source": "del_src"}).json()
        assert len(feats_before) == 2

        resp = client.delete("/api/sources/del_src")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"deleted": "del_src", "features_removed": 2}

        assert client.get("/api/sources/del_src").status_code == 404
        feats_after = client.get("/api/features", params={"source": "del_src"}).json()
        assert feats_after == []

    def test_delete_returns_404_when_missing(self, client):
        resp = client.delete("/api/sources/never_added")
        assert resp.status_code == 404
        assert "Source not found" in resp.json()["detail"]

    def test_delete_with_no_features_returns_zero(self, client, tmp_path):
        _add_source(client, "empty_src", str(tmp_path / "empty.parquet"))
        resp = client.delete("/api/sources/empty_src")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": "empty_src", "features_removed": 0}


class TestBulkDeleteSources:
    """POST /api/sources/bulk/delete — mirrors the features bulk-delete shape."""

    def test_bulk_delete_cascades_features_for_each_source(self, client, parquet_file):
        _add_source(client, "bulk_a", parquet_file)
        _add_source(client, "bulk_b", parquet_file)
        client.post("/api/sources/bulk_a/scan")
        client.post("/api/sources/bulk_b/scan")
        # Each parquet file has 2 columns → 2 features per source = 4 total.
        feats_before = client.get("/api/features").json()
        assert len([f for f in feats_before if f["name"].startswith(("bulk_a.", "bulk_b."))]) == 4

        resp = client.post(
            "/api/sources/bulk/delete",
            json={"names": ["bulk_a", "bulk_b"], "confirm": True},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert sorted(body["deleted"]) == ["bulk_a", "bulk_b"]
        assert body["features_removed"] == 4
        assert body["requested"] == 2

        # Both sources gone, features cascade-removed.
        assert client.get("/api/sources/bulk_a").status_code == 404
        assert client.get("/api/sources/bulk_b").status_code == 404
        feats_after = client.get("/api/features").json()
        assert [f for f in feats_after if f["name"].startswith(("bulk_a.", "bulk_b."))] == []

    def test_bulk_delete_unknown_name_aborts_with_400(self, client, parquet_file):
        """All-or-nothing: an unknown name in the batch must not delete the
        valid sources in the same payload."""
        _add_source(client, "bulk_keep", parquet_file)
        resp = client.post(
            "/api/sources/bulk/delete",
            json={"names": ["bulk_keep", "does_not_exist"], "confirm": True},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail["invalid_names"] == ["does_not_exist"]
        # The valid source is still present.
        assert client.get("/api/sources/bulk_keep").status_code == 200

    def test_bulk_delete_without_confirm_returns_400(self, client, parquet_file):
        _add_source(client, "bulk_safe", parquet_file)
        resp = client.post(
            "/api/sources/bulk/delete",
            json={"names": ["bulk_safe"], "confirm": False},
        )
        assert resp.status_code == 400
        assert "confirm" in resp.json()["detail"]
        # Confirms it actually didn't delete the source.
        assert client.get("/api/sources/bulk_safe").status_code == 200

    def test_bulk_delete_empty_names_returns_422(self, client):
        """Pydantic ``min_length=1`` on ``names`` rejects an empty list."""
        resp = client.post(
            "/api/sources/bulk/delete",
            json={"names": [], "confirm": True},
        )
        assert resp.status_code == 422


class TestUpdateSource:
    def test_update_description(self, client, tmp_path):
        _add_source(client, "upd_src", str(tmp_path / "u.parquet"))
        resp = client.patch("/api/sources/upd_src", json={"description": "new desc"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "new desc"

        # Re-read confirms persistence.
        got = client.get("/api/sources/upd_src").json()
        assert got["description"] == "new desc"

    def test_update_format(self, client, tmp_path):
        _add_source(client, "fmt_src", str(tmp_path / "f.csv"))
        resp = client.patch("/api/sources/fmt_src", json={"format": "csv"})
        assert resp.status_code == 200
        assert resp.json()["format"] == "csv"

    def test_update_missing_returns_404(self, client):
        resp = client.patch("/api/sources/nope", json={"description": "x"})
        assert resp.status_code == 404


class TestSourceImpact:
    def test_impact_counts_features_and_groups(self, client, parquet_file, tmp_path):
        _add_source(client, "impact_src", parquet_file)
        client.post("/api/sources/impact_src/scan")

        # Create a group and add features to it.
        client.post("/api/groups", json={"name": "grp1", "description": "test"})
        feats = client.get("/api/features", params={"source": "impact_src"}).json()
        feature_names = [f["name"] for f in feats]
        client.post("/api/groups/grp1/members", json={"feature_specs": feature_names})

        resp = client.get("/api/sources/impact_src/impact")
        assert resp.status_code == 200
        body = resp.json()
        assert body["features_count"] == 2
        assert body["groups"] == [{"name": "grp1", "feature_count": 2}]

    def test_impact_for_missing_source_returns_zero(self, client):
        resp = client.get("/api/sources/ghost/impact")
        # 200 with zero counts — UI can render delete dialog idempotently.
        assert resp.status_code == 200
        assert resp.json() == {"features_count": 0, "groups": []}


class TestScanLogs:
    def test_scan_records_audit_row(self, client, parquet_file):
        _add_source(client, "log_src", parquet_file)

        scan_resp = client.post("/api/sources/log_src/scan")
        assert scan_resp.status_code == 200
        scan_body = scan_resp.json()
        assert scan_body["features_registered"] == 2
        assert scan_body["features_added"] == 2
        assert scan_body["features_updated"] == 0
        assert scan_body["scan_log_id"]

        logs = client.get("/api/sources/log_src/scan-logs").json()
        assert len(logs) == 1
        assert logs[0]["id"] == scan_body["scan_log_id"]
        assert logs[0]["status"] == "success"
        assert logs[0]["features_added"] == 2
        assert logs[0]["triggered_by"] == "api"
        assert logs[0]["duration_seconds"] is not None

    def test_second_scan_records_updates(self, client, parquet_file):
        _add_source(client, "rescan_src", parquet_file)
        client.post("/api/sources/rescan_src/scan")
        client.post("/api/sources/rescan_src/scan")

        logs = client.get("/api/sources/rescan_src/scan-logs").json()
        assert len(logs) == 2
        # Newest first; second scan saw existing columns → updated, not added.
        assert logs[0]["features_added"] == 0
        assert logs[0]["features_updated"] == 2
        assert logs[1]["features_added"] == 2

    def test_scan_failure_records_failed_log(self, client, tmp_path):
        # Register a source pointing at a path that doesn't exist so the
        # scan handler raises and the failure path runs.
        _add_source(client, "bad_src", str(tmp_path / "missing.parquet"))
        resp = client.post("/api/sources/bad_src/scan")
        assert resp.status_code == 400

        logs = client.get("/api/sources/bad_src/scan-logs").json()
        assert len(logs) == 1
        assert logs[0]["status"] == "failed"
        assert logs[0]["error_message"]

    def test_scan_logs_limit(self, client, parquet_file):
        _add_source(client, "limit_src", parquet_file)
        for _ in range(5):
            client.post("/api/sources/limit_src/scan")
        logs = client.get("/api/sources/limit_src/scan-logs", params={"limit": 3}).json()
        assert len(logs) == 3

    def test_scan_logs_for_missing_source_returns_404(self, client):
        resp = client.get("/api/sources/never_added/scan-logs")
        assert resp.status_code == 404

    def test_scan_logs_cascade_when_source_deleted(self, client, parquet_file):
        _add_source(client, "cascade_log_src", parquet_file)
        client.post("/api/sources/cascade_log_src/scan")
        assert len(client.get("/api/sources/cascade_log_src/scan-logs").json()) == 1

        client.delete("/api/sources/cascade_log_src")
        # Source is gone — endpoint 404s instead of leaking orphan rows.
        assert client.get("/api/sources/cascade_log_src/scan-logs").status_code == 404
