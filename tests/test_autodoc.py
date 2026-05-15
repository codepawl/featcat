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

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
    ) -> str:
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

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
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


class TestAutodocChangedBy:
    """Regression for drift bug #1 in docs/BACKLOG.md (UAT finding
    'feature_versions.changed_by is unknown for LLM-generated docs'):
    a save triggered by AutodocPlugin must attribute the version snapshot
    to the LLM, not whoever happens to be logged in on the host.
    """

    def test_changed_by_is_llm_model(self, db_with_features: CatalogDB) -> None:
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        # MockAutodocLLM does not set a model attribute; autodoc falls back
        # to "unknown" model_name → use the LLM's class name to make the
        # test deterministic without depending on environment.
        llm.model = "test-stub-llm"  # type: ignore[attr-defined]

        result = plugin.execute(db_with_features, llm, feature_name="src.age")
        assert result.status == "success"

        feature = db_with_features.get_feature_by_name("src.age")
        assert feature is not None
        versions = db_with_features.list_feature_versions(feature.id)
        doc_versions = [v for v in versions if v.get("change_type") == "doc"]
        assert doc_versions, "autodoc save should produce a 'doc' version row"
        latest_doc = doc_versions[0]
        assert latest_doc["changed_by"] == "llm:test-stub-llm", (
            f"expected 'llm:test-stub-llm', got {latest_doc['changed_by']!r}"
        )
        assert latest_doc["changed_by"] != "unknown"

    def test_changed_by_falls_back_to_autodoc_when_no_model(self, db_with_features: CatalogDB) -> None:
        """If the LLM client does not expose a model name (older stubs),
        the autodoc path should still produce a meaningful attribution
        rather than the generic 'unknown'."""
        plugin = AutodocPlugin()
        llm = MockAutodocLLM()
        # Force getattr(llm, "model", "unknown") to return "unknown".
        # The class has no `model` attribute by default, but verify
        # explicitly by deleting if a parent set one.
        if hasattr(llm, "model"):
            del llm.model

        result = plugin.execute(db_with_features, llm, feature_name="src.age")
        assert result.status == "success"

        feature = db_with_features.get_feature_by_name("src.age")
        assert feature is not None
        versions = db_with_features.list_feature_versions(feature.id)
        doc_versions = [v for v in versions if v.get("change_type") == "doc"]
        assert doc_versions
        latest_doc = doc_versions[0]
        assert latest_doc["changed_by"] == "autodoc", f"expected 'autodoc' fallback, got {latest_doc['changed_by']!r}"

    def test_explicit_changed_by_overrides_resolve_user(self, db_with_features: CatalogDB) -> None:
        """Save-side regression: save_feature_doc must honour an explicit
        ``changed_by`` kwarg from any caller (not only the autodoc plugin),
        so the catalog-layer fix is verifiable in isolation from the LLM
        client wiring above."""
        feature = db_with_features.get_feature_by_name("src.age")
        assert feature is not None
        db_with_features.save_feature_doc(
            feature.id,
            {"short_description": "stub"},
            model_used="m",
            changed_by="llm:custom",
        )
        versions = db_with_features.list_feature_versions(feature.id)
        doc_versions = [v for v in versions if v.get("change_type") == "doc"]
        assert doc_versions
        assert doc_versions[0]["changed_by"] == "llm:custom"
