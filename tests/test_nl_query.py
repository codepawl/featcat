"""Tests for the Natural Language Query plugin."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.llm.base import BaseLLM
from featcat.plugins.nl_query import NLQueryPlugin, _fuzzy_search, _is_vietnamese

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class MockNLQueryLLM(BaseLLM):
    RESPONSE = json.dumps(
        {
            "results": [
                {"feature": "src.session_count", "score": 0.95, "reason": "Counts user sessions"},
                {"feature": "src.data_usage", "score": 0.80, "reason": "Measures data consumption"},
            ],
            "interpretation": "Looking for user behavior features",
            "follow_up": "Try: features related to churn",
        }
    )

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.3) -> str:
        return self.RESPONSE

    def stream(self, prompt: str, system: str | None = None, temperature: float = 0.3) -> Iterator[str]:
        yield self.RESPONSE

    def health_check(self) -> bool:
        return True


@pytest.fixture()
def db_with_features(tmp_path: Path) -> CatalogDB:
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    for col, tags in [
        ("session_count", ["behavior", "30d"]),
        ("data_usage", ["behavior", "usage"]),
        ("churn_label", ["target", "churn"]),
        ("device_id", ["identifier"]),
    ]:
        db.upsert_feature(
            Feature(
                name=f"src.{col}",
                data_source_id=source.id,
                column_name=col,
                dtype="int64",
                tags=tags,
            )
        )
    return db


class TestVietnameseDetection:
    def test_english(self):
        assert _is_vietnamese("features about churn") is False

    def test_vietnamese(self):
        assert _is_vietnamese("tìm các feature liên quan đến churn") is True

    def test_mixed(self):
        assert _is_vietnamese("features liên quan đến user behavior") is True


class TestFuzzySearch:
    def test_keyword_match(self, db_with_features: CatalogDB):
        results = _fuzzy_search(db_with_features, "session")
        names = [r["feature"] for r in results]
        assert "src.session_count" in names

    def test_tag_match(self, db_with_features: CatalogDB):
        results = _fuzzy_search(db_with_features, "churn")
        names = [r["feature"] for r in results]
        assert "src.churn_label" in names


class TestNLQuery:
    def test_llm_query(self, db_with_features: CatalogDB):
        plugin = NLQueryPlugin()
        llm = MockNLQueryLLM()
        result = plugin.execute(db_with_features, llm, query="user behavior features")

        assert result.status == "success"
        assert result.data["method"] == "llm"
        assert len(result.data["results"]) == 2
        assert result.data["results"][0]["score"] >= result.data["results"][1]["score"]
        assert result.data.get("interpretation")

    def test_fallback_mode(self, db_with_features: CatalogDB):
        plugin = NLQueryPlugin()
        result = plugin.execute(db_with_features, None, query="session", fallback_only=True)

        assert result.status == "success"
        assert result.data["method"] == "fuzzy_search"
        names = [r["feature"] for r in result.data["results"]]
        assert "src.session_count" in names

    def test_no_query(self, db_with_features: CatalogDB):
        plugin = NLQueryPlugin()
        result = plugin.execute(db_with_features, None)
        assert result.status == "error"

    def test_plugin_properties(self):
        plugin = NLQueryPlugin()
        assert plugin.name == "nl_query"
