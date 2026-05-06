"""Tests for T2.1 in-web notifications — backend + API + event hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "notif.db"))
    db.init_db()
    return db


@pytest.fixture
def db_with_feature(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "notif.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    db.upsert_feature(
        Feature(
            name="src.col_0",
            data_source_id=src.id,
            column_name="col_0",
            dtype="float64",
        )
    )
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class TestNotificationCRUD:
    def test_create_then_list(self, db: LocalBackend) -> None:
        nid = db.create_notification("info", "Hello", body="Welcome")
        assert nid
        items = db.list_notifications()
        assert len(items) == 1
        assert items[0]["title"] == "Hello"
        assert items[0]["read_at"] is None

    def test_unread_only_filter(self, db: LocalBackend) -> None:
        n1 = db.create_notification("info", "A")
        db.create_notification("info", "B")
        db.mark_notification_read(n1)
        unread = db.list_notifications(unread_only=True)
        assert len(unread) == 1
        assert unread[0]["title"] == "B"

    def test_count_unread(self, db: LocalBackend) -> None:
        n1 = db.create_notification("info", "A")
        db.create_notification("info", "B")
        db.create_notification("info", "C")
        assert db.count_unread_notifications() == 3
        db.mark_notification_read(n1)
        assert db.count_unread_notifications() == 2

    def test_mark_read_unknown_id_returns_false(self, db: LocalBackend) -> None:
        assert db.mark_notification_read("nope") is False

    def test_mark_read_idempotent(self, db: LocalBackend) -> None:
        nid = db.create_notification("info", "A")
        assert db.mark_notification_read(nid) is True
        # Already read — second call returns False (no-op).
        assert db.mark_notification_read(nid) is False

    def test_mark_all_read(self, db: LocalBackend) -> None:
        for i in range(3):
            db.create_notification("info", f"N{i}")
        n = db.mark_all_notifications_read()
        assert n == 3
        assert db.count_unread_notifications() == 0

    def test_pagination(self, db: LocalBackend) -> None:
        for i in range(5):
            db.create_notification("info", f"N{i:02d}")
        page1 = db.list_notifications(limit=2, offset=0)
        page2 = db.list_notifications(limit=2, offset=2)
        assert len(page1) == 2 and len(page2) == 2
        assert {p["title"] for p in page1}.isdisjoint({p["title"] for p in page2})


# --------------------------------------------------------------------------- #
# Event hooks                                                                 #
# --------------------------------------------------------------------------- #


class TestEventHooks:
    def test_action_item_creation_emits_notification(self, db_with_feature: LocalBackend) -> None:
        feat = db_with_feature.get_feature_by_name("src.col_0")
        assert feat is not None
        before = db_with_feature.count_unread_notifications()
        db_with_feature.create_action_item(
            feat.id,
            source="discovery",
            title="rename",
            recommendation="use snake_case",
        )
        assert db_with_feature.count_unread_notifications() == before + 1
        items = db_with_feature.list_notifications(unread_only=True)
        # action notifications carry the action's link.
        assert any(i["kind"] == "action" and i["feature_id"] == feat.id for i in items)


# --------------------------------------------------------------------------- #
# API                                                                         #
# --------------------------------------------------------------------------- #


class TestNotificationsAPI:
    def test_list_endpoint(self, db: LocalBackend) -> None:
        db.create_notification("info", "A")
        db.create_notification("drift", "B", severity="warning")
        resp = _client(db).get("/api/notifications")
        assert resp.status_code == 200
        body = resp.json()
        assert {item["title"] for item in body} == {"A", "B"}

    def test_unread_count_endpoint(self, db: LocalBackend) -> None:
        for i in range(2):
            db.create_notification("info", f"N{i}")
        resp = _client(db).get("/api/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 2}

    def test_mark_read_endpoint(self, db: LocalBackend) -> None:
        nid = db.create_notification("info", "A")
        client = _client(db)
        resp = client.post(f"/api/notifications/{nid}/read")
        assert resp.status_code == 200 and resp.json()["read"] is True
        # Second call → 404 because read_at is no longer NULL (mark_notification_read
        # only matches unread rows).
        resp2 = client.post(f"/api/notifications/{nid}/read")
        assert resp2.status_code == 404

    def test_mark_read_unknown_404(self, db: LocalBackend) -> None:
        resp = _client(db).post("/api/notifications/nope/read")
        assert resp.status_code == 404

    def test_mark_all_read_endpoint(self, db: LocalBackend) -> None:
        for i in range(3):
            db.create_notification("info", f"N{i}")
        resp = _client(db).post("/api/notifications/read-all")
        assert resp.status_code == 200 and resp.json()["marked_read"] == 3
        assert db.count_unread_notifications() == 0
