"""Tests for T1.4a — server-side pagination + filter pushdown + TTL cache."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.server.cache import cache_get, invalidate

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def seeded_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "pag.db"))
    db.init_db()
    src_a = db.add_source(DataSource(name="src_a", path="/a.parquet"))
    src_b = db.add_source(DataSource(name="src_b", path="/b.parquet"))
    for i in range(15):
        db.upsert_feature(
            Feature(
                name=f"src_a.col_{i:02d}",
                data_source_id=src_a.id,
                column_name=f"col_{i:02d}",
                dtype="int64" if i % 2 == 0 else "float64",
                tags=["pii"] if i % 3 == 0 else ["clean"],
                owner="data-team" if i < 5 else "ml-team",
            )
        )
    for i in range(5):
        db.upsert_feature(
            Feature(
                name=f"src_b.col_{i:02d}",
                data_source_id=src_b.id,
                column_name=f"col_{i:02d}",
                dtype="string",
                tags=["geo"],
            )
        )
    db.save_feature_doc(db.get_feature_by_name("src_a.col_00").id, {"short_description": "doc"})
    return db


# --------------------------------------------------------------------------- #
# Backend filter + pagination                                                 #
# --------------------------------------------------------------------------- #


class TestListFeaturesFilters:
    def test_no_filter_returns_all(self, seeded_db: LocalBackend) -> None:
        assert len(seeded_db.list_features()) == 20

    def test_source_filter(self, seeded_db: LocalBackend) -> None:
        assert len(seeded_db.list_features(source_name="src_a")) == 15
        assert len(seeded_db.list_features(source_name="src_b")) == 5

    def test_dtype_filter(self, seeded_db: LocalBackend) -> None:
        assert len(seeded_db.list_features(dtype="int64")) == 8  # 0,2,4,6,8,10,12,14 in src_a
        assert len(seeded_db.list_features(dtype="string")) == 5

    def test_owner_filter(self, seeded_db: LocalBackend) -> None:
        assert len(seeded_db.list_features(owner="data-team")) == 5

    def test_tag_filter(self, seeded_db: LocalBackend) -> None:
        # Tag stored as JSON string; LIKE match on quoted token
        pii = seeded_db.list_features(tag="pii")
        assert all("pii" in f.tags for f in pii)

    def test_search_filter(self, seeded_db: LocalBackend) -> None:
        results = seeded_db.list_features(search="src_b")
        assert all(f.name.startswith("src_b") for f in results)

    def test_has_doc_true(self, seeded_db: LocalBackend) -> None:
        results = seeded_db.list_features(has_doc=True)
        assert len(results) == 1
        assert results[0].name == "src_a.col_00"

    def test_has_doc_false(self, seeded_db: LocalBackend) -> None:
        results = seeded_db.list_features(has_doc=False)
        assert all(f.name != "src_a.col_00" for f in results)
        assert len(results) == 19

    def test_limit_offset(self, seeded_db: LocalBackend) -> None:
        page1 = seeded_db.list_features(limit=5, offset=0, sort="name", order="asc")
        page2 = seeded_db.list_features(limit=5, offset=5, sort="name", order="asc")
        assert len(page1) == len(page2) == 5
        assert {f.id for f in page1}.isdisjoint({f.id for f in page2})

    def test_sort_validation(self, seeded_db: LocalBackend) -> None:
        with pytest.raises(ValueError, match="sort must be"):
            seeded_db.list_features(sort="; DROP TABLE features --")
        with pytest.raises(ValueError, match="order must be"):
            seeded_db.list_features(order="malicious")

    def test_count_features_matches_filter(self, seeded_db: LocalBackend) -> None:
        assert seeded_db.count_features() == 20
        assert seeded_db.count_features(source_name="src_a") == 15
        assert seeded_db.count_features(dtype="string") == 5
        assert seeded_db.count_features(has_doc=True) == 1


# --------------------------------------------------------------------------- #
# /api/features envelope                                                      #
# --------------------------------------------------------------------------- #


class TestPaginationEnvelope:
    def _client(self, db: LocalBackend) -> TestClient:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_no_limit_returns_list(self, seeded_db: LocalBackend) -> None:
        client = self._client(seeded_db)
        resp = client.get("/api/features")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 20

    def test_limit_returns_envelope(self, seeded_db: LocalBackend) -> None:
        client = self._client(seeded_db)
        resp = client.get("/api/features", params={"limit": 5, "offset": 0})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"items", "total", "limit", "offset"}
        assert body["total"] == 20
        assert body["limit"] == 5
        assert body["offset"] == 0
        assert len(body["items"]) == 5

    def test_paginated_filter_pushdown(self, seeded_db: LocalBackend) -> None:
        client = self._client(seeded_db)
        resp = client.get("/api/features", params={"limit": 50, "source": "src_b"})
        body = resp.json()
        assert body["total"] == 5
        assert all(item["name"].startswith("src_b") for item in body["items"])


# --------------------------------------------------------------------------- #
# TTL cache                                                                   #
# --------------------------------------------------------------------------- #


class TestCache:
    def setup_method(self) -> None:
        invalidate()  # clean cache state between tests

    def test_sources_endpoint_caches(self, seeded_db: LocalBackend) -> None:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: seeded_db
        client = TestClient(app)
        # Cache miss
        assert cache_get("sources:list") is None
        client.get("/api/sources")
        assert cache_get("sources:list") is not None
        # Subsequent reads hit cache
        cached = cache_get("sources:list")
        client.get("/api/sources")
        assert cache_get("sources:list") is cached  # same object reference

    def test_add_source_invalidates_cache(self, seeded_db: LocalBackend) -> None:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: seeded_db
        client = TestClient(app)
        client.get("/api/sources")  # populate cache
        assert cache_get("sources:list") is not None
        client.post("/api/sources", json={"name": "src_c", "path": "/c.parquet"})
        assert cache_get("sources:list") is None  # invalidated

    def test_invalidate_prefix_drops_only_matching(self) -> None:
        from featcat.server.cache import cache_set

        cache_set("sources:list", [1])
        cache_set("dashboard:stats", {"x": 1})
        cache_set("other:thing", "y")
        assert invalidate(prefix="sources:") == 1
        assert cache_get("sources:list") is None
        assert cache_get("dashboard:stats") is not None
        assert cache_get("other:thing") is not None
