"""Tests for admin endpoints (LLM cache stats / clear)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.db import CatalogDB
from featcat.server import create_app
from featcat.utils.cache import ResponseCache

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "admin.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    seed = CatalogDB(db_path)
    seed.init_db()
    seed.close()

    cache = ResponseCache(db_path)
    cache.put("hello", "world", ttl_seconds=3600, system="system")
    cache.put("foo", "bar", ttl_seconds=3600)
    cache.close()

    app = create_app()
    with TestClient(app) as c:
        yield c


def test_cache_stats(client: TestClient) -> None:
    resp = client.get("/api/admin/cache/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert "active" in data and "expired" in data


def test_cache_clear(client: TestClient) -> None:
    resp = client.post("/api/admin/cache/clear")
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 2

    after = client.get("/api/admin/cache/stats").json()
    assert after["total"] == 0


def test_cache_clear_expired(client: TestClient) -> None:
    resp = client.post("/api/admin/cache/clear-expired")
    assert resp.status_code == 200
    assert "deleted" in resp.json()
