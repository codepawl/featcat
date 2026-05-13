"""Tests for glossary endpoint."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.db import CatalogDB
from featcat.server import create_app
from featcat.server.glossary import GLOSSARY, get_glossary

if TYPE_CHECKING:
    from pathlib import Path


def test_glossary_module_has_core_terms() -> None:
    data = get_glossary()
    terms = data["terms"]
    for key in ("health_score", "health_grade", "psi", "drift_severity", "action_item"):
        assert key in terms, f"missing glossary term: {key}"
        assert terms[key]["label"]
        assert terms[key]["description"]


def test_glossary_thresholds_consistent() -> None:
    psi = GLOSSARY["psi"]
    assert "thresholds" in psi
    severities = {t.get("severity") for t in psi["thresholds"]}
    assert severities >= {"healthy", "warning", "critical"}


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "g.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    seed = CatalogDB(db_path)
    seed.init_db()
    seed.close()
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_endpoint_returns_glossary(client: TestClient) -> None:
    resp = client.get("/api/docs/glossary")
    assert resp.status_code == 200
    body = resp.json()
    assert "terms" in body
    assert "health_score" in body["terms"]
