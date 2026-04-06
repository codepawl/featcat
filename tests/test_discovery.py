"""Tests for the Feature Discovery plugin."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.llm.base import BaseLLM
from featcat.plugins.discovery import DiscoveryPlugin

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class MockDiscoveryLLM(BaseLLM):
    """Mock LLM that returns a discovery response."""

    RESPONSE = json.dumps(
        {
            "existing_features": [
                {"name": "src.session_count", "relevance": 0.95, "reason": "Session count is key for churn"},
                {"name": "src.complaint_count", "relevance": 0.85, "reason": "Complaints predict churn"},
            ],
            "new_feature_suggestions": [
                {
                    "name": "session_trend_7d",
                    "source": "src",
                    "column_expression": "slope of session_count over 7 days",
                    "reason": "Captures declining engagement",
                },
            ],
            "summary": "Focus on behavioral and complaint features for churn prediction",
        }
    )

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.3, json_mode: bool = False) -> str:
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
    for col in ["session_count", "complaint_count", "data_usage", "churn_label"]:
        db.upsert_feature(
            Feature(
                name=f"src.{col}",
                data_source_id=source.id,
                column_name=col,
                dtype="int64",
                tags=["behavior"],
                stats={"mean": 10, "std": 5, "null_ratio": 0.01},
            )
        )
    return db


class TestDiscovery:
    def test_execute_success(self, db_with_features: CatalogDB):
        plugin = DiscoveryPlugin()
        llm = MockDiscoveryLLM()
        result = plugin.execute(db_with_features, llm, use_case="churn prediction")

        assert result.status == "success"
        assert len(result.data["existing_features"]) == 2
        assert result.data["existing_features"][0]["relevance"] >= result.data["existing_features"][1]["relevance"]
        assert len(result.data["new_feature_suggestions"]) == 1
        assert result.data["summary"]

    def test_execute_no_use_case(self, db_with_features: CatalogDB):
        plugin = DiscoveryPlugin()
        llm = MockDiscoveryLLM()
        result = plugin.execute(db_with_features, llm)

        assert result.status == "error"
        assert "use_case" in result.errors[0]

    def test_plugin_properties(self):
        plugin = DiscoveryPlugin()
        assert plugin.name == "discovery"
        assert plugin.description
