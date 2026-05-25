"""Tests for group versioning + freeze + export.

Covers the LocalBackend ``freeze_group``/``list_group_versions``/
``get_group_version`` methods plus the four routes:
``POST /api/groups/{name}/freeze``, ``GET .../versions``,
``GET .../versions/{n}``, ``GET .../versions/{n}/export``.
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_group(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "freeze.db"))
    db.init_db()
    src = db.add_source(
        DataSource(
            name="src",
            path="/data/src.parquet",
            format="parquet",
            entity_key="user_id",
            event_timestamp_column="event_ts",
            created_timestamp_column="created_ts",
        )
    )
    f1 = db.upsert_feature(
        Feature(
            name="src.user_age",
            data_source_id=src.id,
            column_name="user_age",
            dtype="int64",
            description="user age in years",
            tags=["user", "demographic"],
            stats={"mean": 35.2, "null_pct": 0.01},
        )
    )
    f2 = db.upsert_feature(
        Feature(
            name="src.signup_country",
            data_source_id=src.id,
            column_name="signup_country",
            dtype="string",
            description="ISO-3166 country code at signup",
            tags=["user"],
        )
    )
    group = db.create_group(FeatureGroup(name="user-profile", description="User profile features", owner="alice"))
    db.add_group_members(group.id, [f1.id, f2.id])
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


# ---------------------------------------------------------------------------
# Backend method tests
# ---------------------------------------------------------------------------


class TestFreezeGroup:
    def test_first_freeze_is_v1(self, db_with_group: LocalBackend) -> None:
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        version = db_with_group.freeze_group(group.id, note="initial", frozen_by="alice")
        assert version.version_number == 1
        assert version.note == "initial"
        assert version.frozen_by == "alice"

    def test_second_freeze_increments(self, db_with_group: LocalBackend) -> None:
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        v1 = db_with_group.freeze_group(group.id)
        v2 = db_with_group.freeze_group(group.id, note="after edit")
        assert (v1.version_number, v2.version_number) == (1, 2)

    def test_snapshot_captures_member_fields(self, db_with_group: LocalBackend) -> None:
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        version = db_with_group.freeze_group(group.id)
        snapshot = json.loads(version.snapshot_json)
        assert snapshot["group"]["name"] == "user-profile"
        assert snapshot["version_number"] == 1
        names = {f["name"] for f in snapshot["features"]}
        assert names == {"src.user_age", "src.signup_country"}
        # Per-feature reproducibility fields
        age = next(f for f in snapshot["features"] if f["name"] == "src.user_age")
        assert age["dtype"] == "int64"
        assert age["source_path"] == "/data/src.parquet"
        assert age["source_format"] == "parquet"
        assert age["source_entity_key"] == "user_id"
        assert age["source_event_timestamp_column"] == "event_ts"
        assert age["source_created_timestamp_column"] == "created_ts"
        assert age["tags"] == ["user", "demographic"]
        assert age["stats"]["mean"] == 35.2

    def test_list_versions_newest_first(self, db_with_group: LocalBackend) -> None:
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        db_with_group.freeze_group(group.id, note="v1")
        db_with_group.freeze_group(group.id, note="v2")
        db_with_group.freeze_group(group.id, note="v3")
        versions = db_with_group.list_group_versions(group.id)
        assert [v.version_number for v in versions] == [3, 2, 1]

    def test_get_version_returns_one(self, db_with_group: LocalBackend) -> None:
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        db_with_group.freeze_group(group.id)
        v = db_with_group.get_group_version(group.id, 1)
        assert v is not None
        assert v.version_number == 1
        assert db_with_group.get_group_version(group.id, 99) is None


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


class TestFreezeRoutes:
    def test_freeze_creates_version(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        resp = client.post("/api/groups/user-profile/freeze", json={"note": "baseline", "frozen_by": "alice"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["version_number"] == 1
        assert body["member_count"] == 2
        assert body["note"] == "baseline"
        assert body["frozen_by"] == "alice"

    def test_freeze_empty_group_400(self, db_with_group: LocalBackend) -> None:
        # Drain the group first.
        group = db_with_group.get_group_by_name("user-profile")
        assert group is not None
        for f in db_with_group.list_group_members(group.id):
            db_with_group.remove_group_member(group.id, f.id)

        resp = _client(db_with_group).post("/api/groups/user-profile/freeze", json={})
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    def test_freeze_unknown_group_404(self, db_with_group: LocalBackend) -> None:
        resp = _client(db_with_group).post("/api/groups/does-not-exist/freeze", json={})
        assert resp.status_code == 404

    def test_list_versions_returns_summaries(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={"note": "v1"})
        client.post("/api/groups/user-profile/freeze", json={"note": "v2"})
        resp = client.get("/api/groups/user-profile/versions")
        assert resp.status_code == 200
        rows = resp.json()
        assert [r["version_number"] for r in rows] == [2, 1]
        assert all(r["member_count"] == 2 for r in rows)

    def test_get_version_includes_snapshot(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={})
        resp = client.get("/api/groups/user-profile/versions/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["version_number"] == 1
        assert body["snapshot"]["group"]["name"] == "user-profile"
        assert {f["name"] for f in body["snapshot"]["features"]} == {"src.user_age", "src.signup_country"}
        # All features still present → no warnings on a fresh snapshot.
        assert body["warnings"] == []

    def test_get_version_404_for_unknown_n(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={})
        resp = client.get("/api/groups/user-profile/versions/99")
        assert resp.status_code == 404


class TestExportRoutes:
    def test_export_json_roundtrips(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={"note": "for export"})
        resp = client.get("/api/groups/user-profile/versions/1/export?format=json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        body = json.loads(resp.content)
        assert body["group"]["name"] == "user-profile"
        assert {f["name"] for f in body["features"]} == {"src.user_age", "src.signup_country"}
        assert body["warnings"] == []

    def test_export_csv_has_headers_and_rows(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={})
        resp = client.get("/api/groups/user-profile/versions/1/export?format=csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        reader = csv.DictReader(io.StringIO(resp.content.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 2
        assert {r["name"] for r in rows} == {"src.user_age", "src.signup_country"}
        assert reader.fieldnames is not None
        assert "source_path" in reader.fieldnames
        assert "deleted_after_freeze" in reader.fieldnames

    def test_export_invalid_format_422(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={})
        resp = client.get("/api/groups/user-profile/versions/1/export?format=xml")
        # FastAPI's pattern validation rejects with 422.
        assert resp.status_code == 422

    def test_deleted_feature_flagged_in_export(self, db_with_group: LocalBackend) -> None:
        client = _client(db_with_group)
        client.post("/api/groups/user-profile/freeze", json={})

        # Delete one feature post-freeze.
        country = db_with_group.get_feature_by_name("src.signup_country")
        assert country is not None
        db_with_group.bulk_delete_features([country.id])

        resp = client.get("/api/groups/user-profile/versions/1/export?format=json")
        assert resp.status_code == 200
        body = json.loads(resp.content)
        flagged = {f["name"]: f["deleted_after_freeze"] for f in body["features"]}
        assert flagged == {"src.user_age": False, "src.signup_country": True}
        assert any("signup_country" in w for w in body["warnings"])
