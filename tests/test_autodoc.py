"""Tests for the Auto Documentation plugin."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.llm.base import BaseLLM
from featcat.plugins.autodoc import AutodocPlugin, export_docs_markdown, get_doc, get_doc_stats

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class MockAutodocLLM(BaseLLM):
    """Mock LLM that returns autodoc responses."""

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.3, json_mode: bool = False) -> str:
        if "batch" in prompt.lower() or "following features" in prompt.lower():
            return json.dumps(
                [
                    {
                        "feature_name": "src.age",
                        "short_description": "Customer age",
                        "long_description": "Age of the customer in years.",
                        "expected_range": "18-100",
                        "potential_issues": "Missing values for new customers",
                        "suggested_tags": ["demographic"],
                    },
                    {
                        "feature_name": "src.revenue",
                        "short_description": "Monthly revenue",
                        "long_description": "Revenue from the customer in the last month.",
                        "expected_range": ">= 0",
                        "potential_issues": "Outliers from enterprise accounts",
                        "suggested_tags": ["financial"],
                    },
                ]
            )
        return json.dumps(
            {
                "short_description": "Customer age in years",
                "long_description": "Age of the customer. Used for segmentation.",
                "expected_range": "18-100",
                "potential_issues": "Nulls for new signups",
                "suggested_tags": ["demographic", "user"],
            }
        )

    def stream(self, prompt: str, system: str | None = None, temperature: float = 0.3) -> Iterator[str]:
        yield self.generate(prompt, system, temperature)

    def health_check(self) -> bool:
        return True


@pytest.fixture()
def db_with_features(tmp_path: Path) -> CatalogDB:
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    for col, dtype in [("age", "int64"), ("revenue", "double")]:
        db.upsert_feature(
            Feature(
                name=f"src.{col}",
                data_source_id=source.id,
                column_name=col,
                dtype=dtype,
                stats={"mean": 30, "std": 10, "null_ratio": 0.05},
            )
        )
    return db


class TestAutodoc:
    def test_document_single(self, db_with_features: CatalogDB):
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        result = plugin.execute(db_with_features, llm, feature_name="src.age")

        assert result.status == "success"
        assert result.data["documented"] == 1

        doc = get_doc(db_with_features, "src.age")
        assert doc is not None
        assert "age" in doc["short_description"].lower()

    def test_document_not_found(self, db_with_features: CatalogDB):
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        result = plugin.execute(db_with_features, llm, feature_name="nonexistent")
        assert result.status == "error"

    def test_doc_stats(self, db_with_features: CatalogDB):
        stats = get_doc_stats(db_with_features)
        assert stats["total_features"] == 2
        assert stats["documented"] == 0
        assert stats["coverage"] == 0.0

        # Generate a doc
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        plugin.execute(db_with_features, llm, feature_name="src.age")

        stats = get_doc_stats(db_with_features)
        assert stats["documented"] == 1
        assert stats["coverage"] == 50.0

    def test_export_markdown(self, db_with_features: CatalogDB):
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        plugin.execute(db_with_features, llm, feature_name="src.age")

        md = export_docs_markdown(db_with_features)
        assert "# Feature Documentation" in md
        assert "src.age" in md
        assert "src.revenue" in md

    def test_get_doc_nonexistent(self, db_with_features: CatalogDB):
        doc = get_doc(db_with_features, "nonexistent")
        assert doc is None

    def test_plugin_properties(self):
        plugin = AutodocPlugin()
        assert plugin.name == "autodoc"
