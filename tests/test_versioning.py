"""Tests for feature metadata version tracking."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature


@pytest.fixture()
def db_with_feature(tmp_path):
    """Create a catalog with one feature for version testing."""
    db_path = str(tmp_path / "test_versions.db")
    db = LocalBackend(db_path)
    db.init_db()

    pq_path = tmp_path / "test.parquet"
    table = pa.table({"user_id": pa.array([1, 2, 3]), "score": pa.array([0.5, 0.8, 0.3])})
    pq.write_table(table, pq_path)

    source = DataSource(name="test_src", path=str(pq_path))
    db.add_source(source)
    feature = Feature(
        name="test_src.score", data_source_id=source.id,
        column_name="score", dtype="float64",
    )
    db.upsert_feature(feature)

    yield db, feature
    db.close()


class TestInitialVersion:
    def test_upsert_creates_v1(self, db_with_feature):
        db, feature = db_with_feature
        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 1
        v = versions[0]
        assert v["version"] == 1
        assert v["change_type"] == "metadata"
        assert v["change_summary"] == "Initial registration via scan"

    def test_upsert_existing_no_duplicate(self, db_with_feature):
        """Re-upserting same feature should not create another version."""
        db, feature = db_with_feature
        db.upsert_feature(feature)  # second upsert
        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 1  # still just v1


class TestMetadataVersioning:
    def test_description_update_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.update_feature_metadata(feature.id, description="New description")

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 2  # v1 (initial) + v2 (update)
        v = versions[0]  # latest
        assert v["change_type"] == "metadata"
        assert v["previous_value"]["description"] == ""
        assert v["new_value"]["description"] == "New description"

    def test_tags_update_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.update_feature_tags(feature.id, ["churn", "30d"])

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 2
        v = versions[0]
        assert v["change_type"] == "tags"
        assert v["new_value"]["tags"] == ["churn", "30d"]

    def test_version_increments_per_feature(self, db_with_feature):
        db, feature = db_with_feature
        db.update_feature_metadata(feature.id, description="First")
        db.update_feature_metadata(feature.id, description="Second")
        db.update_feature_metadata(feature.id, owner="annx9")

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 4  # v1 initial + 3 updates
        assert versions[0]["version"] == 4
        assert versions[3]["version"] == 1


class TestDocVersioning:
    def test_doc_save_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.save_feature_doc(feature.id, {"short_description": "A score metric"})

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 2
        v = versions[0]
        assert v["change_type"] == "doc"
        assert "short_description" in v["new_value"]

    def test_doc_update_captures_previous(self, db_with_feature):
        db, feature = db_with_feature
        db.save_feature_doc(feature.id, {"short_description": "First"})
        db.save_feature_doc(feature.id, {"short_description": "Second"})

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 3  # v1 initial + 2 doc updates
        latest = versions[0]
        assert latest["previous_value"]["short_description"] == "First"
        assert latest["new_value"]["short_description"] == "Second"


class TestHintVersioning:
    def test_hint_set_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.set_feature_hint(feature.id, "Computed from last 30 days")

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 2
        v = versions[0]
        assert v["change_type"] == "hints"
        assert v["previous_value"]["generation_hints"] is None
        assert v["new_value"]["generation_hints"] == "Computed from last 30 days"

    def test_hint_clear_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.set_feature_hint(feature.id, "Some hint")
        db.clear_feature_hint(feature.id)

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 3  # v1 initial + set + clear
        latest = versions[0]
        assert latest["change_type"] == "hints"
        assert latest["previous_value"]["generation_hints"] == "Some hint"
        assert latest["new_value"]["generation_hints"] is None


class TestDefinitionVersioning:
    def test_definition_set_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "SELECT score FROM users", "sql")

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 2
        v = versions[0]
        assert v["change_type"] == "definition"
        assert v["new_value"]["definition"] == "SELECT score FROM users"
        assert v["new_value"]["definition_type"] == "sql"

    def test_definition_clear_creates_version(self, db_with_feature):
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "SELECT 1", "sql")
        db.clear_feature_definition(feature.id)

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 3  # v1 initial + set + clear
        latest = versions[0]
        assert latest["change_type"] == "definition"
        assert latest["previous_value"]["definition"] == "SELECT 1"
        assert latest["new_value"]["definition"] is None


class TestNoVersioning:
    def test_stats_update_no_version(self, db_with_feature):
        """Stats changes should NOT create additional versions beyond initial."""
        db, feature = db_with_feature
        db.conn.execute(
            "UPDATE features SET stats = ? WHERE id = ?",
            ('{"mean": 0.5}', feature.id),
        )
        db.conn.commit()

        versions = db.list_feature_versions(feature.id)
        assert len(versions) == 1  # only the initial registration


class TestRecentVersions:
    def test_recent_returns_across_features(self, db_with_feature):
        db, feature = db_with_feature

        feature2 = Feature(
            name="test_src.user_id", data_source_id=feature.data_source_id,
            column_name="user_id", dtype="int64",
        )
        db.upsert_feature(feature2)

        db.update_feature_metadata(feature.id, description="Updated")
        db.update_feature_metadata(feature2.id, owner="dev")

        recent = db.get_recent_versions(limit=10, days=7)
        # 2 initial + 2 updates = 4 total
        assert len(recent) == 4
        names = [r["feature_name"] for r in recent]
        assert "test_src.user_id" in names
        assert "test_src.score" in names


class TestVersionAPI:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from featcat.server.app import build_app

        db_path = str(tmp_path / "test_ver.db")
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

        def _raise(**kwargs):
            raise RuntimeError("no LLM")

        monkeypatch.setattr("featcat.llm.create_llm", _raise)

        app = build_app()
        with TestClient(app) as c:
            pq_path = tmp_path / "t.parquet"
            table = pa.table({"col": pa.array([1, 2])})
            pq.write_table(table, pq_path)
            c.post("/api/sources", json={"path": str(pq_path), "name": "s1"})
            c.post("/api/sources/s1/scan")
            yield c

    def test_versions_endpoint(self, client):
        client.patch("/api/features/by-name", params={"name": "s1.col"}, json={"description": "test"})

        resp = client.get("/api/features/by-name/versions", params={"name": "s1.col"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2  # initial + update
        assert data[0]["change_type"] == "metadata"

    def test_recent_versions_endpoint(self, client):
        resp = client.get("/api/versions/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1  # at least the initial registration
        assert "feature_name" in data[0]

    def test_initial_version_on_scan(self, client):
        """Scanning creates initial version entries."""
        resp = client.get("/api/features/by-name/versions", params={"name": "s1.col"})
        assert resp.status_code == 200
        data = resp.json()
        assert any(v["change_summary"] == "Initial registration via scan" for v in data)
