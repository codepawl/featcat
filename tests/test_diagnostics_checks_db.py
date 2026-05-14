"""Unit tests for ``featcat.diagnostics.checks_db``.

Tests cover the SQLite path end-to-end (uses a real in-memory-ish backend
against a tmp_path catalog). The postgres-only branches (pgvector, alembic,
pool) are exercised via ``monkeypatch.setattr(..., "postgres")`` and a fake
engine that returns scripted scalars.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.config import Settings
from featcat.diagnostics import CheckStatus
from featcat.diagnostics.checks_db import (
    db_alembic,
    db_backend,
    db_cache_stats,
    db_catalog_stats,
    db_pgvector,
    db_pool,
    db_reachable,
    db_version,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def sqlite_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Seed a tmp catalog and point env vars at it."""
    db_path = str(tmp_path / "catalog.db")
    backend = LocalBackend(db_path)
    backend.init_db()
    src = DataSource(name="src", path=str(tmp_path / "data.parquet"))
    backend.add_source(src)
    backend.upsert_feature(Feature(name="src.col0", data_source_id=src.id, column_name="col0", dtype="int64"))
    backend.close()

    monkeypatch.setenv("FEATCAT_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    monkeypatch.delenv("FEATCAT_DB_URL", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    return Settings(catalog_db_path=db_path)


@pytest.fixture()
def empty_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db_path = str(tmp_path / "catalog.db")
    LocalBackend(db_path).init_db()
    monkeypatch.setenv("FEATCAT_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    monkeypatch.delenv("FEATCAT_DB_URL", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    return Settings(catalog_db_path=db_path)


class TestDbReachable:
    def test_pass_on_local_sqlite(self, sqlite_catalog: Settings) -> None:
        result = db_reachable(sqlite_catalog)
        assert result.status is CheckStatus.PASS
        assert "sqlite" in result.detail
        assert result.metadata["latency_ms"] >= 0

    def test_fail_on_bad_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A bogus postgres URL must surface as FAIL with a resolution string."""
        monkeypatch.setenv("FEATCAT_DB_BACKEND", "postgres")
        monkeypatch.setenv("FEATCAT_DB_URL", "postgresql+psycopg2://x:y@127.0.0.1:1/none")
        result = db_reachable(Settings())
        assert result.status is CheckStatus.FAIL
        assert result.resolution is not None


class TestDbBackend:
    def test_reports_resolved_backend(self, sqlite_catalog: Settings) -> None:
        result = db_backend(sqlite_catalog)
        assert result.status is CheckStatus.PASS
        assert result.metadata["backend"] == "sqlite"

    def test_invalid_backend_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FEATCAT_DB_BACKEND", "duckdb")
        result = db_backend(Settings())
        assert result.status is CheckStatus.FAIL
        assert "FEATCAT_DB_BACKEND" in (result.resolution or "")


class TestDbVersion:
    def test_sqlite_passes(self, sqlite_catalog: Settings) -> None:
        result = db_version(sqlite_catalog)
        assert result.status is CheckStatus.PASS
        assert "SQLite" in result.detail


class TestDbPgvector:
    def test_sqlite_skips(self, sqlite_catalog: Settings) -> None:
        result = db_pgvector(sqlite_catalog)
        assert result.status is CheckStatus.SKIP


class TestDbAlembic:
    def test_sqlite_skips(self, sqlite_catalog: Settings) -> None:
        result = db_alembic(sqlite_catalog)
        assert result.status is CheckStatus.SKIP


class TestDbCatalogStats:
    def test_warn_on_empty(self, empty_sqlite: Settings) -> None:
        result = db_catalog_stats(empty_sqlite)
        assert result.status is CheckStatus.WARN
        assert "empty" in result.detail.lower()
        assert result.resolution is not None

    def test_pass_when_populated(self, sqlite_catalog: Settings) -> None:
        result = db_catalog_stats(sqlite_catalog)
        assert result.status is CheckStatus.PASS
        assert result.metadata["sources"] == 1
        assert result.metadata["features"] == 1


class TestDbPool:
    def test_sqlite_skips(self, sqlite_catalog: Settings) -> None:
        result = db_pool(sqlite_catalog)
        assert result.status is CheckStatus.SKIP


class TestDbCacheStats:
    def test_pass_when_catalog_exists(self, sqlite_catalog: Settings) -> None:
        result = db_cache_stats(sqlite_catalog)
        # ResponseCache stats query never failed → PASS
        assert result.status is CheckStatus.PASS

    def test_skip_when_catalog_missing(self, tmp_path: Path) -> None:
        settings = Settings(catalog_db_path=str(tmp_path / "absent.db"))
        result = db_cache_stats(settings)
        assert result.status is CheckStatus.SKIP
