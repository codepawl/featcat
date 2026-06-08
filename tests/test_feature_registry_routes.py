from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


def _write_parquet(path: Path, data: dict[str, list[object]]) -> None:
    pq.write_table(pa.table(data), path)


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


class TestFeatureRegistryRoutes:
    def test_views_and_sets_roundtrip(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "feature-registry.db"))
        db.init_db()
        source_path = tmp_path / "src.parquet"
        _write_parquet(
            source_path,
            {
                "bad_signal_days_7d": [1],
            },
        )
        src = db.add_source(DataSource(name="src", path=str(source_path)))
        db.upsert_feature(
            Feature(
                name="src.bad_signal_days_7d",
                data_source_id=src.id,
                column_name="bad_signal_days_7d",
                entity_grain="customer_id",
            )
        )

        client = _client(db)
        resp = client.post(
            "/api/feature-views",
            json={
                "name": "customer_network_view",
                "entity": "customer",
                "source_name": "src",
                "feature_names": ["src.bad_signal_days_7d"],
                "owner": "platform",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["entity"] == "customer"

        resp = client.post(
            "/api/feature-sets",
            json={
                "name": "churn_features_v1",
                "target_entity": "customer",
                "feature_names": ["src.bad_signal_days_7d"],
                "owner": "ml-platform",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["target_entity"] == "customer"

        resp = client.get("/api/feature-views/by-name", params={"name": "customer_network_view"})
        assert resp.status_code == 200
        resp = client.get("/api/feature-sets/by-name", params={"name": "churn_features_v1"})
        assert resp.status_code == 200

    def test_feature_view_rejects_missing_source_column(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "feature-registry.db"))
        db.init_db()
        source_path = tmp_path / "src.parquet"
        _write_parquet(source_path, {"other_column": [1]})
        src = db.add_source(DataSource(name="src", path=str(source_path)))
        db.upsert_feature(
            Feature(
                name="src.bad_signal_days_7d",
                data_source_id=src.id,
                column_name="bad_signal_days_7d",
                entity_grain="customer_id",
            )
        )

        resp = _client(db).post(
            "/api/feature-views",
            json={
                "name": "customer_network_view",
                "entity": "customer",
                "source_name": "src",
                "feature_names": ["src.bad_signal_days_7d"],
                "owner": "platform",
            },
        )
        assert resp.status_code == 400
        assert "missing column" in resp.json()["detail"].lower()
