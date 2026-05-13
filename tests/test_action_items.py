"""Tests for action_items lifecycle (drift -> action -> apply)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.server import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def db_with_feature(tmp_path: Path) -> CatalogDB:
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    db.upsert_feature(Feature(name="src.col_a", data_source_id=source.id, column_name="col_a", dtype="int64"))
    yield db
    db.close()


class TestActionItemBackend:
    def test_create_and_get(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        assert feat is not None
        item_id = db.create_action_item(
            feature_id=feat.id,
            source="manual",
            title="Update tags",
            recommendation="Add owner tag",
            context={"reason": "missing owner"},
        )
        assert item_id
        item = db.get_action_item(item_id)
        assert item is not None
        assert item["status"] == "pending"
        assert item["title"] == "Update tags"
        assert item["context"] == {"reason": "missing owner"}
        assert item["feature_name"] == "src.col_a"

    def test_list_filter(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        db.create_action_item(feat.id, "drift_alert", "T1", "rec1")
        db.create_action_item(feat.id, "manual", "T2", "rec2")

        all_items = db.list_action_items()
        assert len(all_items) == 2

        only_manual = db.list_action_items(source="manual")
        assert len(only_manual) == 1
        assert only_manual[0]["title"] == "T2"

        only_drift = db.list_action_items(source="drift_alert")
        assert len(only_drift) == 1

    def test_status_transitions(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        item_id = db.create_action_item(feat.id, "manual", "T", "rec")

        db.update_action_item_status(item_id, "applied", applied_by="alice", change_summary="done")
        item = db.get_action_item(item_id)
        assert item["status"] == "applied"
        assert item["applied_by"] == "alice"
        assert item["applied_at"] is not None
        assert item["change_summary"] == "done"

    def test_invalid_status(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        item_id = db.create_action_item(feat.id, "manual", "T", "rec")
        with pytest.raises(ValueError):
            db.update_action_item_status(item_id, "bogus")

    def test_find_pending_action_dedup(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        db.create_action_item(feat.id, "drift_alert", "Same title", "rec")

        existing = db.find_pending_action(feat.id, "drift_alert", "Same title")
        assert existing is not None

        # After apply, it should no longer be returned as pending
        db.update_action_item_status(existing["id"], "applied")
        assert db.find_pending_action(feat.id, "drift_alert", "Same title") is None

    def test_count(self, db_with_feature: CatalogDB) -> None:
        db = db_with_feature
        feat = db.get_feature_by_name("src.col_a")
        db.create_action_item(feat.id, "manual", "T1", "rec1")
        db.create_action_item(feat.id, "manual", "T2", "rec2")
        assert db.count_action_items() == 2
        assert db.count_action_items(status="pending") == 2
        assert db.count_action_items(status="applied") == 0


class TestActionItemAPI:
    @pytest.fixture()
    def client(self, tmp_path: Path, monkeypatch):
        db_path = str(tmp_path / "api.db")
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

        # Pre-seed a feature
        seed = CatalogDB(db_path)
        seed.init_db()
        source = DataSource(name="src", path="/data/x.parquet")
        seed.add_source(source)
        seed.upsert_feature(Feature(name="src.col_a", data_source_id=source.id, column_name="col_a", dtype="int64"))
        seed.close()

        app = create_app()
        with TestClient(app) as c:
            yield c

    def test_post_creates_pending(self, client: TestClient) -> None:
        resp = client.post(
            "/api/actions",
            json={
                "feature_name": "src.col_a",
                "source": "manual",
                "title": "API test",
                "recommendation": "do it",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["title"] == "API test"
        item_id = body["id"]

        listing = client.get("/api/actions?status=pending").json()
        assert any(item["id"] == item_id for item in listing)

    def test_patch_apply(self, client: TestClient) -> None:
        post = client.post(
            "/api/actions",
            json={"feature_name": "src.col_a", "source": "manual", "title": "X", "recommendation": "Y"},
        )
        item_id = post.json()["id"]

        patch = client.patch(
            f"/api/actions/{item_id}",
            json={"status": "applied", "applied_by": "tester", "change_summary": "fixed"},
        )
        assert patch.status_code == 200
        assert patch.json()["status"] == "applied"

    def test_invalid_source_rejected(self, client: TestClient) -> None:
        resp = client.post(
            "/api/actions",
            json={"feature_name": "src.col_a", "source": "bogus", "title": "T", "recommendation": "R"},
        )
        assert resp.status_code == 400

    def test_unknown_feature(self, client: TestClient) -> None:
        resp = client.post(
            "/api/actions",
            json={"feature_name": "no.such.feature", "source": "manual", "title": "T", "recommendation": "R"},
        )
        assert resp.status_code == 404

    def test_count_endpoint(self, client: TestClient) -> None:
        client.post(
            "/api/actions",
            json={"feature_name": "src.col_a", "source": "manual", "title": "C1", "recommendation": "R"},
        )
        resp = client.get("/api/actions/count?status=pending")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1
