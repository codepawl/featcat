"""Tests for T1.3a — bulk feature operations API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_features(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "bulk.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    for i in range(5):
        db.upsert_feature(
            Feature(
                name=f"src.col_{i}",
                data_source_id=src.id,
                column_name=f"col_{i}",
                dtype="int64",
                tags=["pii"] if i < 2 else [],
            )
        )
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _ids(db: LocalBackend, *names: str) -> list[str]:
    out = []
    for n in names:
        f = db.get_feature_by_name(n)
        assert f is not None
        out.append(f.id)
    return out


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class TestBulkUpdateTagsBackend:
    def test_add_unions_with_existing(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0", "src.col_2")
        # col_0 has [pii], col_2 has []. Add ['churn']: col_0 → {pii,churn}, col_2 → {churn}
        n = db_with_features.bulk_update_tags(ids, "add", ["churn"])
        assert n == 2
        f0 = db_with_features.get_feature_by_name("src.col_0")
        f2 = db_with_features.get_feature_by_name("src.col_2")
        assert f0 is not None and "churn" in f0.tags and "pii" in f0.tags
        assert f2 is not None and f2.tags == ["churn"]

    def test_replace_overwrites(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0")
        db_with_features.bulk_update_tags(ids, "replace", ["new"])
        f = db_with_features.get_feature_by_name("src.col_0")
        assert f is not None and f.tags == ["new"]

    def test_remove_filters_out(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0")
        db_with_features.bulk_update_tags(ids, "remove", ["pii"])
        f = db_with_features.get_feature_by_name("src.col_0")
        assert f is not None and "pii" not in f.tags

    def test_no_op_skipped(self, db_with_features: LocalBackend) -> None:
        # col_2 has [] — removing 'pii' is a no-op, should not bump version count.
        ids = _ids(db_with_features, "src.col_2")
        n = db_with_features.bulk_update_tags(ids, "remove", ["pii"])
        assert n == 0

    def test_unknown_action_raises(self, db_with_features: LocalBackend) -> None:
        with pytest.raises(ValueError, match="action must be"):
            db_with_features.bulk_update_tags([], "bad", ["x"])


class TestBulkGroupBackend:
    def test_add_to_group(self, db_with_features: LocalBackend) -> None:
        g = db_with_features.create_group(FeatureGroup(name="grp"))
        ids = _ids(db_with_features, "src.col_0", "src.col_1")
        n = db_with_features.bulk_group_action(g.id, ids, "add_to")
        assert n == 2
        assert db_with_features.count_group_members(g.id) == 2

    def test_remove_from_group(self, db_with_features: LocalBackend) -> None:
        g = db_with_features.create_group(FeatureGroup(name="grp"))
        ids = _ids(db_with_features, "src.col_0", "src.col_1", "src.col_2")
        db_with_features.bulk_group_action(g.id, ids, "add_to")
        # Remove col_0 + col_2; col_3 is a no-op (never added).
        targets = _ids(db_with_features, "src.col_0", "src.col_2", "src.col_3")
        n = db_with_features.bulk_group_action(g.id, targets, "remove_from")
        assert n == 2
        assert db_with_features.count_group_members(g.id) == 1


class TestBulkDeleteBackend:
    def test_deletes_features_and_dependents(self, db_with_features: LocalBackend) -> None:
        # Set up: doc + baseline + group membership for col_0 so we exercise the
        # non-cascade cleanup path.
        f0 = db_with_features.get_feature_by_name("src.col_0")
        assert f0 is not None
        db_with_features.save_feature_doc(f0.id, {"short_description": "doc"})
        db_with_features.save_baseline(f0.id, {"mean": 1.0})
        g = db_with_features.create_group(FeatureGroup(name="grp"))
        db_with_features.add_group_members(g.id, [f0.id])

        n = db_with_features.bulk_delete_features([f0.id])
        assert n == 1
        assert db_with_features.get_feature_by_name("src.col_0") is None
        assert db_with_features.get_feature_doc(f0.id) is None
        assert db_with_features.get_baseline(f0.id) is None
        assert db_with_features.count_group_members(g.id) == 0  # CASCADE


# --------------------------------------------------------------------------- #
# API                                                                         #
# --------------------------------------------------------------------------- #


class TestBulkTagsEndpoint:
    def test_happy_path(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0", "src.col_1")
        resp = _client(db_with_features).post(
            "/api/features/bulk/tags",
            json={"feature_ids": ids, "action": "add", "tags": ["churn"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] >= 1
        assert body["requested"] == 2

    def test_invalid_id_returns_400_with_list(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0") + ["bad-id"]
        resp = _client(db_with_features).post(
            "/api/features/bulk/tags",
            json={"feature_ids": ids, "action": "add", "tags": ["x"]},
        )
        assert resp.status_code == 400
        assert "bad-id" in resp.json()["detail"]["invalid_ids"]

    def test_invalid_action_400(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0")
        resp = _client(db_with_features).post(
            "/api/features/bulk/tags",
            json={"feature_ids": ids, "action": "bogus", "tags": ["x"]},
        )
        assert resp.status_code == 400


class TestBulkGroupsEndpoint:
    def test_add_to_then_remove_from(self, db_with_features: LocalBackend) -> None:
        g = db_with_features.create_group(FeatureGroup(name="grp"))
        ids = _ids(db_with_features, "src.col_0", "src.col_1")
        client = _client(db_with_features)
        r1 = client.post(
            "/api/features/bulk/groups",
            json={"feature_ids": ids, "action": "add_to", "group_id": g.id},
        )
        assert r1.status_code == 200 and r1.json()["changed"] == 2
        r2 = client.post(
            "/api/features/bulk/groups",
            json={"feature_ids": ids, "action": "remove_from", "group_id": g.id},
        )
        assert r2.status_code == 200 and r2.json()["changed"] == 2


class TestBulkDeleteEndpoint:
    def test_requires_confirm(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_0")
        resp = _client(db_with_features).post(
            "/api/features/bulk/delete",
            json={"feature_ids": ids},
        )
        assert resp.status_code == 400
        assert "confirm" in resp.json()["detail"].lower()
        # Feature still present
        assert db_with_features.get_feature_by_name("src.col_0") is not None

    def test_with_confirm_deletes(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features, "src.col_3", "src.col_4")
        resp = _client(db_with_features).post(
            "/api/features/bulk/delete",
            json={"feature_ids": ids, "confirm": True},
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2
        assert db_with_features.get_feature_by_name("src.col_3") is None
        assert db_with_features.get_feature_by_name("src.col_4") is None
