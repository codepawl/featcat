"""Tests for T3.1a — feature certification workflow (backend + API)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "cert.db"))
    db.init_db()
    return db


@pytest.fixture
def feature_minimal(db: LocalBackend) -> Feature:
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    return db.upsert_feature(
        Feature(
            name="src.col_0",
            data_source_id=src.id,
            column_name="col_0",
            dtype="int64",
        )
    )


@pytest.fixture
def feature_ready(db: LocalBackend) -> Feature:
    """Feature meeting every certification requirement.

    Uses a distinct source name (``src_ready``) so this fixture composes
    cleanly with ``feature_minimal`` in tests that need both populated —
    the schema's UNIQUE on data_sources.name would otherwise collide.
    """
    src = db.get_source_by_name("src_ready") or db.add_source(DataSource(name="src_ready", path="/y.parquet"))
    feat = db.upsert_feature(
        Feature(
            name="src_ready.col_ready",
            data_source_id=src.id,
            column_name="col_ready",
            dtype="float64",
            owner="data-team",
        )
    )
    db.save_feature_doc(feat.id, {"short_description": "ready feature"})
    db.save_baseline(feat.id, {"mean": 1.0})
    g = db.create_group(FeatureGroup(name="prod"))
    db.add_group_members(g.id, [feat.id])
    return feat


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class TestCertificationReadiness:
    def test_minimal_feature_missing_everything(self, db: LocalBackend, feature_minimal: Feature) -> None:
        readiness = db.check_certification_readiness(feature_minimal.id)
        assert readiness["ready"] is False
        # Bare feature → missing doc, baseline, owner, group/standalone.
        assert {"documentation", "baseline", "owner", "group_membership_or_standalone"} <= set(readiness["missing"])

    def test_fully_ready_passes(self, db: LocalBackend, feature_ready: Feature) -> None:
        assert db.check_certification_readiness(feature_ready.id) == {"ready": True, "missing": []}

    def test_standalone_tag_substitutes_for_group(self, db: LocalBackend) -> None:
        src = db.add_source(DataSource(name="src", path="/x.parquet"))
        feat = db.upsert_feature(
            Feature(
                name="src.col_solo",
                data_source_id=src.id,
                column_name="col_solo",
                dtype="float64",
                owner="data-team",
                tags=["standalone"],
            )
        )
        db.save_feature_doc(feat.id, {"short_description": "solo"})
        db.save_baseline(feat.id, {"mean": 1.0})
        readiness = db.check_certification_readiness(feat.id)
        assert readiness["ready"] is True

    def test_unknown_feature_not_found(self, db: LocalBackend) -> None:
        assert db.check_certification_readiness("nope") == {"ready": False, "missing": ["feature_not_found"]}


class TestSetFeatureStatus:
    def test_simple_transition_succeeds(self, db: LocalBackend, feature_minimal: Feature) -> None:
        result = db.set_feature_status(feature_minimal.id, "reviewed")
        assert result == {"ok": True, "status": "reviewed", "missing": []}
        feat = db.get_feature_by_name("src.col_0")
        assert feat is not None and feat.status == "reviewed"

    def test_unknown_status_raises(self, db: LocalBackend, feature_minimal: Feature) -> None:
        with pytest.raises(ValueError, match="status must be"):
            db.set_feature_status(feature_minimal.id, "approved")

    def test_certify_blocked_when_not_ready(self, db: LocalBackend, feature_minimal: Feature) -> None:
        result = db.set_feature_status(feature_minimal.id, "certified")
        assert result["ok"] is False
        assert "documentation" in result["missing"]
        # Status didn't change.
        feat = db.get_feature_by_name("src.col_0")
        assert feat is not None and feat.status == "draft"

    def test_certify_passes_when_ready(self, db: LocalBackend, feature_ready: Feature) -> None:
        result = db.set_feature_status(feature_ready.id, "certified", notes="Q3 sign-off")
        assert result["ok"] is True
        feat = db.get_feature_by_name("src_ready.col_ready")
        assert feat is not None and feat.status == "certified"
        assert feat.status_notes == "Q3 sign-off"

    def test_transition_creates_version_snapshot(self, db: LocalBackend, feature_ready: Feature) -> None:
        # Capture version count before / after.
        before = db.list_feature_versions(feature_ready.id)
        db.set_feature_status(feature_ready.id, "reviewed")
        after = db.list_feature_versions(feature_ready.id)
        assert len(after) == len(before) + 1
        assert after[0]["change_type"] == "status"

    def test_no_op_transition_skips_snapshot(self, db: LocalBackend, feature_minimal: Feature) -> None:
        before = db.list_feature_versions(feature_minimal.id)
        db.set_feature_status(feature_minimal.id, "draft")
        after = db.list_feature_versions(feature_minimal.id)
        assert len(after) == len(before)


class TestListByStatus:
    def test_returns_only_matching(self, db: LocalBackend, feature_minimal: Feature, feature_ready: Feature) -> None:
        db.set_feature_status(feature_ready.id, "reviewed")
        drafts = db.list_features_by_status("draft")
        assert {f.name for f in drafts} == {feature_minimal.name}
        reviewed = db.list_features_by_status("reviewed")
        assert {f.name for f in reviewed} == {feature_ready.name}


# --------------------------------------------------------------------------- #
# API                                                                         #
# --------------------------------------------------------------------------- #


class TestCertificationAPI:
    def test_readiness_endpoint(self, db: LocalBackend, feature_ready: Feature) -> None:
        resp = _client(db).get(
            "/api/features/by-name/certification-readiness",
            params={"name": "src_ready.col_ready"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ready": True, "missing": []}

    def test_readiness_404(self, db: LocalBackend) -> None:
        resp = _client(db).get("/api/features/by-name/certification-readiness", params={"name": "nope"})
        assert resp.status_code == 404

    def test_status_set_happy(self, db: LocalBackend, feature_ready: Feature) -> None:
        resp = _client(db).post(
            "/api/features/by-name/status",
            params={"name": "src_ready.col_ready"},
            json={"status": "certified", "notes": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "certified"

    def test_status_set_certified_blocked(self, db: LocalBackend, feature_minimal: Feature) -> None:
        resp = _client(db).post(
            "/api/features/by-name/status",
            params={"name": "src.col_0"},
            json={"status": "certified"},
        )
        assert resp.status_code == 422
        assert "missing" in resp.json()["detail"]

    def test_status_set_unknown_status_400(self, db: LocalBackend, feature_minimal: Feature) -> None:
        resp = _client(db).post(
            "/api/features/by-name/status",
            params={"name": "src.col_0"},
            json={"status": "approved"},
        )
        assert resp.status_code == 400

    def test_status_set_404(self, db: LocalBackend) -> None:
        resp = _client(db).post(
            "/api/features/by-name/status",
            params={"name": "nope"},
            json={"status": "draft"},
        )
        assert resp.status_code == 404
