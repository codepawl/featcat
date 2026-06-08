from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import Entity

if TYPE_CHECKING:
    from pathlib import Path


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


def _seed(db: LocalBackend) -> None:
    db.upsert_entity(Entity(name="customer", primary_keys=["customer_id"], join_keys=["customer_id"]))
    db.upsert_entity(Entity(name="contract", primary_keys=["contract_id"], join_keys=["contract_id", "customer_id"]))


class TestEntityRoutes:
    def test_list_and_get(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "entities.db"))
        db.init_db()
        _seed(db)

        client = _client(db)
        resp = client.get("/api/entities")
        assert resp.status_code == 200
        assert [row["name"] for row in resp.json()] == ["contract", "customer"]

        resp = client.get("/api/entities/by-name", params={"name": "customer"})
        assert resp.status_code == 200
        assert resp.json()["primary_keys"] == ["customer_id"]

    def test_upsert_relationship(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "relationships.db"))
        db.init_db()
        _seed(db)

        client = _client(db)
        resp = client.post(
            "/api/entity-relationships",
            json={
                "name": "customer_has_contracts",
                "left_entity": "customer",
                "right_entity": "contract",
                "relation_type": "one_to_many",
                "join_keys": [{"left_key": "customer_id", "right_key": "customer_id"}],
                "description": "One customer can have many contracts",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["relation_type"] == "one_to_many"

        resp = client.get("/api/entity-relationships", params={"left_entity": "customer"})
        assert resp.status_code == 200
        assert [row["name"] for row in resp.json()] == ["customer_has_contracts"]
