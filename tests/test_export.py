"""Tests for feature data export."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.exporter import export_features


@pytest.fixture()
def catalog_with_sources(tmp_path):
    """Create a catalog with two sources and their parquet files."""
    from featcat.catalog.local import LocalBackend

    # Create parquet files
    users_path = tmp_path / "users.parquet"
    users = pa.table({
        "user_id": pa.array([1, 2, 3, 4, 5]),
        "session_count": pa.array([10, 20, 30, 40, 50]),
        "churn_label": pa.array([0, 1, 0, 1, 0]),
    })
    pq.write_table(users, users_path)

    devices_path = tmp_path / "devices.parquet"
    devices = pa.table({
        "user_id": pa.array([1, 2, 3, 4, 5]),
        "cpu_usage": pa.array([0.5, 0.8, 0.3, 0.9, 0.1]),
        "memory_usage": pa.array([2.0, 4.0, 1.0, 3.0, 5.0]),
    })
    pq.write_table(devices, devices_path)

    # No common column file
    events_path = tmp_path / "events.parquet"
    events = pa.table({
        "event_id": pa.array([100, 200, 300]),
        "event_type": pa.array(["click", "view", "scroll"]),
    })
    pq.write_table(events, events_path)

    db_path = str(tmp_path / "test.db")
    db = LocalBackend(db_path)
    db.init_db()

    # Add sources and scan
    from featcat.catalog.models import DataSource, Feature
    from featcat.catalog.scanner import scan_source

    for name, path in [("users", str(users_path)), ("devices", str(devices_path)), ("events", str(events_path))]:
        source = DataSource(name=name, path=path)
        db.add_source(source)
        columns = scan_source(path)
        for col in columns:
            feature = Feature(
                name=f"{name}.{col.column_name}",
                data_source_id=source.id,
                column_name=col.column_name,
                dtype=col.dtype,
                stats=col.stats,
            )
            db.upsert_feature(feature)

    yield db
    db.close()


class TestSingleSourceExport:
    def test_basic_export(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        output = str(tmp_path / "export.parquet")
        result = export_features(
            feature_specs=["users.session_count", "users.churn_label"],
            db=db,
            output_path=output,
        )
        assert result.feature_count == 2
        assert result.row_count == 5
        assert result.sources_used == ["users"]
        assert result.join_column is None
        assert Path(output).exists()
        assert result.file_size > 0

        # Verify parquet content
        t = pq.read_table(output)
        assert set(t.column_names) == {"session_count", "churn_label"}
        assert t.num_rows == 5

    def test_csv_format(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        output = str(tmp_path / "export.csv")
        result = export_features(
            feature_specs=["users.session_count"],
            db=db,
            output_path=output,
            fmt="csv",
        )
        assert result.feature_count == 1
        assert Path(output).exists()
        content = Path(output).read_text()
        assert "session_count" in content
        lines = content.strip().split("\n")
        assert len(lines) == 6  # header + 5 rows


class TestMultiSourceExport:
    def test_auto_detect_join(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        output = str(tmp_path / "merged.parquet")
        result = export_features(
            feature_specs=["users.session_count", "devices.cpu_usage"],
            db=db,
            output_path=output,
        )
        assert result.feature_count == 2
        assert result.join_column == "user_id"
        assert set(result.sources_used) == {"users", "devices"}
        assert result.row_count == 5

        t = pq.read_table(output)
        assert "session_count" in t.column_names
        assert "cpu_usage" in t.column_names

    def test_explicit_join_on(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        output = str(tmp_path / "merged2.parquet")
        result = export_features(
            feature_specs=["users.session_count", "devices.cpu_usage"],
            db=db,
            output_path=output,
            join_on="user_id",
        )
        assert result.join_column == "user_id"
        assert result.row_count == 5

    def test_no_common_column(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        output = str(tmp_path / "fail.parquet")
        with pytest.raises(ValueError, match="No common column"):
            export_features(
                feature_specs=["users.session_count", "events.event_type"],
                db=db,
                output_path=output,
            )


class TestCodeSnippet:
    def test_single_source_snippet(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        result = export_features(
            feature_specs=["users.session_count"],
            db=db,
            output_path=str(tmp_path / "out.parquet"),
        )
        assert "polars" in result.code_snippet
        assert "read_parquet" in result.code_snippet

    def test_csv_snippet(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        result = export_features(
            feature_specs=["users.session_count"],
            db=db,
            output_path=str(tmp_path / "out.csv"),
            fmt="csv",
        )
        assert "read_csv" in result.code_snippet


class TestInvalidInputs:
    def test_no_valid_features(self, catalog_with_sources, tmp_path):
        db = catalog_with_sources
        with pytest.raises(ValueError, match="No valid features"):
            export_features(
                feature_specs=["nonexistent.feature"],
                db=db,
                output_path=str(tmp_path / "out.parquet"),
            )


class TestExportAPI:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from featcat.server.app import build_app

        db_path = str(tmp_path / "test_export.db")
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
        monkeypatch.setenv("FEATCAT_EXPORT_DIR", str(tmp_path / "exports"))

        def _raise(**kwargs):
            raise RuntimeError("no LLM")

        monkeypatch.setattr("featcat.llm.create_llm", _raise)

        app = build_app()
        with TestClient(app) as c:
            # Add a source with features
            users_path = tmp_path / "users.parquet"
            users = pa.table({
                "user_id": pa.array([1, 2, 3]),
                "score": pa.array([0.5, 0.8, 0.3]),
            })
            pq.write_table(users, users_path)
            c.post("/api/sources", json={"path": str(users_path), "name": "users"})
            c.post("/api/sources/users/scan")
            yield c

    def test_export_endpoint(self, client):
        resp = client.post("/api/export", json={
            "feature_specs": ["users.score"],
            "format": "parquet",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["feature_count"] == 1
        assert data["row_count"] == 3
        assert "export_id" in data
        assert "code_snippet" in data

    def test_download_endpoint(self, client):
        resp = client.post("/api/export", json={"feature_specs": ["users.score"]})
        export_id = resp.json()["export_id"]

        dl = client.get(f"/api/export/{export_id}/download")
        assert dl.status_code == 200
        assert len(dl.content) > 0

    def test_export_no_specs(self, client):
        resp = client.post("/api/export", json={})
        assert resp.status_code == 400

    def test_export_invalid_format(self, client):
        resp = client.post("/api/export", json={
            "feature_specs": ["users.score"],
            "format": "xlsx",
        })
        assert resp.status_code == 400

    def test_download_expired(self, client):
        resp = client.get("/api/export/nonexistent/download")
        assert resp.status_code == 404
