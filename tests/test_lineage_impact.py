"""Tests for T1.1 — extended lineage with source-column parents + impact analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import BusinessMetric, DataSource, Feature, FeatureSet, FeatureView

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def lineage_db(tmp_path: Path) -> LocalBackend:
    """Build a small graph:

    src_a.col_x ─→ feat_a1
                 ╲
                  → feat_a2 ─→ feat_b1 (in src_b)
    src_a.col_y ─→ feat_a3
    (orphan: feat_orphan in src_b — no lineage)
    """
    db = LocalBackend(str(tmp_path / "lineage.db"))
    db.init_db()
    a_path = tmp_path / "a.parquet"
    b_path = tmp_path / "b.parquet"
    pq.write_table(pa.table({"feat_a1": [1], "feat_a2": [2], "feat_a3": [3], "col_x": [1], "col_y": [2]}), a_path)
    pq.write_table(pa.table({"feat_b1": [1], "feat_orphan": [0]}), b_path)
    src_a = db.add_source(DataSource(name="src_a", path=str(a_path)))
    src_b = db.add_source(DataSource(name="src_b", path=str(b_path)))

    feat_a1 = db.upsert_feature(
        Feature(name="src_a.feat_a1", data_source_id=src_a.id, column_name="feat_a1", dtype="float64")
    )
    feat_a2 = db.upsert_feature(
        Feature(name="src_a.feat_a2", data_source_id=src_a.id, column_name="feat_a2", dtype="float64")
    )
    feat_a3 = db.upsert_feature(
        Feature(name="src_a.feat_a3", data_source_id=src_a.id, column_name="feat_a3", dtype="int64")
    )
    feat_b1 = db.upsert_feature(
        Feature(name="src_b.feat_b1", data_source_id=src_b.id, column_name="feat_b1", dtype="float64")
    )
    db.upsert_feature(
        Feature(name="src_b.feat_orphan", data_source_id=src_b.id, column_name="feat_orphan", dtype="int64")
    )

    # Source-column → feature edges
    db.add_source_lineage(feat_a1.id, src_a.id, "col_x", transform="raw")
    db.add_source_lineage(feat_a2.id, src_a.id, "col_x", transform="lag 1d")
    db.add_source_lineage(feat_a3.id, src_a.id, "col_y")

    # Feature → feature edge
    db.add_lineage(feat_b1.id, feat_a2.id, transform="aggregate")
    return db


class TestSourceLineage:
    def test_add_source_lineage_persists(self, lineage_db: LocalBackend) -> None:
        impact = lineage_db.get_impact("src_a")
        names = {r["name"] for r in impact}
        assert "src_a.feat_a1" in names
        assert "src_a.feat_a2" in names
        assert "src_a.feat_a3" in names

    def test_column_filter_narrows(self, lineage_db: LocalBackend) -> None:
        col_x_only = lineage_db.get_impact("src_a", column="col_x")
        names = {r["name"] for r in col_x_only}
        assert names == {"src_a.feat_a1", "src_a.feat_a2", "src_b.feat_b1"}
        # feat_a3 (col_y) is excluded; feat_b1 is reachable transitively from feat_a2

    def test_unknown_source_returns_empty(self, lineage_db: LocalBackend) -> None:
        assert lineage_db.get_impact("does_not_exist") == []

    def test_idempotent_add(self, lineage_db: LocalBackend) -> None:
        # Re-adding the same source-column edge is a no-op (ON CONFLICT DO NOTHING).
        src = lineage_db.get_source_by_name("src_a")
        assert src is not None
        feat = lineage_db.get_feature_by_name("src_a.feat_a1")
        assert feat is not None
        before = len(lineage_db.get_impact("src_a"))
        lineage_db.add_source_lineage(feat.id, src.id, "col_x")
        after = len(lineage_db.get_impact("src_a"))
        assert before == after

    def test_remove_source_lineage(self, lineage_db: LocalBackend) -> None:
        src = lineage_db.get_source_by_name("src_a")
        assert src is not None
        feat = lineage_db.get_feature_by_name("src_a.feat_a1")
        assert feat is not None
        lineage_db.remove_source_lineage(feat.id, src.id, "col_x")
        names = {r["name"] for r in lineage_db.get_impact("src_a", column="col_x")}
        assert "src_a.feat_a1" not in names
        assert "src_a.feat_a2" in names  # other col_x edge untouched


class TestImpactDepth:
    def test_direct_children_at_depth_1(self, lineage_db: LocalBackend) -> None:
        impact = lineage_db.get_impact("src_a", column="col_x")
        depth_by_name = {r["name"]: r["depth"] for r in impact}
        assert depth_by_name["src_a.feat_a1"] == 1
        assert depth_by_name["src_a.feat_a2"] == 1

    def test_transitive_at_depth_2(self, lineage_db: LocalBackend) -> None:
        impact = lineage_db.get_impact("src_a", column="col_x")
        depth_by_name = {r["name"]: r["depth"] for r in impact}
        assert depth_by_name["src_b.feat_b1"] == 2  # via feat_a2

    def test_via_chain_recorded(self, lineage_db: LocalBackend) -> None:
        impact = lineage_db.get_impact("src_a", column="col_x")
        by_name = {r["name"]: r for r in impact}
        # Direct rows: via is the source.column they read from.
        assert by_name["src_a.feat_a2"]["via"] == "src_a.col_x"
        # Transitive row: via is the immediate parent feature's name.
        assert by_name["src_b.feat_b1"]["via"] == "src_a.feat_a2"

    def test_max_depth_caps_traversal(self, lineage_db: LocalBackend) -> None:
        # depth=1 cuts off transitive feat_b1
        d1 = lineage_db.get_impact("src_a", column="col_x", max_depth=1)
        assert all(r["depth"] == 1 for r in d1)
        assert "src_b.feat_b1" not in {r["name"] for r in d1}


# --------------------------------------------------------------------------- #
# /api/lineage/impact                                                         #
# --------------------------------------------------------------------------- #


class TestImpactEndpoint:
    def _client(self, db: LocalBackend) -> TestClient:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_impact_endpoint_returns_records(self, lineage_db: LocalBackend) -> None:
        resp = self._client(lineage_db).get("/api/lineage/impact", params={"source": "src_a"})
        assert resp.status_code == 200
        body = resp.json()
        assert {r["name"] for r in body} == {
            "src_a.feat_a1",
            "src_a.feat_a2",
            "src_a.feat_a3",
            "src_b.feat_b1",
        }

    def test_impact_endpoint_column_filter(self, lineage_db: LocalBackend) -> None:
        resp = self._client(lineage_db).get(
            "/api/lineage/impact",
            params={"source": "src_a", "column": "col_x"},
        )
        names = {r["name"] for r in resp.json()}
        assert names == {"src_a.feat_a1", "src_a.feat_a2", "src_b.feat_b1"}

    def test_impact_endpoint_depth_clamp(self, lineage_db: LocalBackend) -> None:
        resp = self._client(lineage_db).get(
            "/api/lineage/impact",
            params={"source": "src_a", "depth": 1},
        )
        body = resp.json()
        assert all(r["depth"] == 1 for r in body)


# --------------------------------------------------------------------------- #
# /api/lineage/full (T1.1c)                                                   #
# --------------------------------------------------------------------------- #


class TestLineageFullEndpoint:
    def _client(self, db: LocalBackend) -> TestClient:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_empty_catalog_returns_empty_graph(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "empty.db"))
        db.init_db()
        resp = self._client(db).get("/api/lineage/full")
        assert resp.status_code == 200
        assert resp.json() == {"nodes": [], "edges": []}

    def test_features_without_edges_returns_empty_graph(self, tmp_path: Path) -> None:
        # The frontend empty-state CTA depends on this: a catalog with features
        # but zero recorded lineage must yield {nodes: [], edges: []}, not the
        # full feature list as orphan nodes.
        db = LocalBackend(str(tmp_path / "no_edges.db"))
        db.init_db()
        src = db.add_source(DataSource(name="src_x", path="/x.parquet"))
        db.upsert_feature(Feature(name="src_x.feat_a", data_source_id=src.id, column_name="feat_a", dtype="float64"))
        db.upsert_feature(Feature(name="src_x.feat_b", data_source_id=src.id, column_name="feat_b", dtype="int64"))
        resp = self._client(db).get("/api/lineage/full")
        assert resp.status_code == 200
        assert resp.json() == {"nodes": [], "edges": []}

    def test_full_endpoint_returns_feature_to_feature_edges(self, lineage_db: LocalBackend) -> None:
        resp = self._client(lineage_db).get("/api/lineage/full")
        assert resp.status_code == 200
        body = resp.json()
        # Only feature→feature edges (source-column edges excluded);
        # the fixture wires exactly one such edge: feat_a2 → feat_b1.
        assert len(body["edges"]) == 1
        edge = body["edges"][0]
        assert edge["child"] == "src_b.feat_b1"
        assert edge["parent"] == "src_a.feat_a2"
        assert edge["transform"] == "aggregate"
        assert edge["detected_method"] == "manual"
        # Nodes are exactly the endpoints of those edges (no orphans, no
        # source-column-only features).
        names = {n["name"] for n in body["nodes"]}
        assert names == {"src_a.feat_a2", "src_b.feat_b1"}
        for n in body["nodes"]:
            assert n["source"] in {"src_a", "src_b"}
            assert "dtype" in n
            assert "owner" in n

    def test_full_endpoint_includes_metrics_and_feature_sets(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "registry_lineage.db"))
        db.init_db()
        source_path = tmp_path / "src.parquet"
        pq.write_table(pa.table({"bad_signal_days_7d": [1, 2, 3]}), source_path)
        src = db.add_source(DataSource(name="src", path=str(source_path)))
        feature = db.upsert_feature(
            Feature(name="src.bad_signal_days_7d", data_source_id=src.id, column_name="bad_signal_days_7d")
        )
        db.upsert_feature_view(
            FeatureView(
                name="customer_network_view",
                entity="customer",
                source_name="src",
                feature_names=[feature.name],
            )
        )
        db.upsert_business_metric(
            BusinessMetric(
                name="network.bad_signal_days_7d",
                business_metric_name="bad_signal_days_7d",
                metric_domain="network_quality",
                lifecycle_stage="consume",
                metric_level="customer",
                entity_grain="customer_id",
                aggregation_rule="sum by customer_id",
                mapped_features=[feature.name],
            )
        )
        db.upsert_feature_set(
            FeatureSet(
                name="churn.customer_set",
                target_entity="customer",
                feature_names=[feature.name],
                rollup_rules={feature.name: "sum by customer_id"},
            )
        )

        resp = self._client(db).get("/api/lineage/full")
        assert resp.status_code == 200
        body = resp.json()

        names = {n["name"] for n in body["nodes"]}
        assert names == {
            "src.bad_signal_days_7d",
            "customer_network_view",
            "network.bad_signal_days_7d",
            "churn.customer_set",
        }
        assert {edge["parent"] for edge in body["edges"]} == {
            "src.bad_signal_days_7d",
            "customer_network_view",
        }
        assert {edge["child"] for edge in body["edges"]} == {
            "src.bad_signal_days_7d",
            "network.bad_signal_days_7d",
            "churn.customer_set",
        }
