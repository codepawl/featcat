"""Verify AutodocPlugin threads the `context` kwarg into the LLM prompt."""

from __future__ import annotations

from unittest.mock import MagicMock

from featcat.plugins.autodoc import AutodocPlugin


def _make_feature() -> MagicMock:
    feature = MagicMock()
    feature.id = "fid"
    feature.name = "src.x"
    feature.column_name = "x"
    feature.dtype = "float64"
    feature.tags = []
    feature.stats = {}
    feature.generation_hints = None
    return feature


def test_autodoc_passes_context_into_prompt(monkeypatch) -> None:
    """If context is provided via execute kwargs, the rendered prompt
    must include an ORG CONTEXT section so the LLM sees it."""
    captured: dict[str, str] = {}

    def fake_generate_json(prompt: str, **kwargs: object) -> dict:
        captured["prompt"] = prompt
        return {
            "short_description": "x",
            "long_description": "y",
            "expected_range": "z",
            "potential_issues": "p",
            "suggested_tags": [],
        }

    llm = MagicMock()
    llm.generate_json.side_effect = fake_generate_json
    llm.model = "test"

    feature = _make_feature()
    db = MagicMock()
    db.get_feature_by_name.return_value = feature
    db.get_source_by_name.return_value = None
    db.save_feature_doc.return_value = None

    monkeypatch.setattr(
        "featcat.catalog.context_builder.build_doc_context", lambda *a, **kw: []
    )

    plugin = AutodocPlugin()
    plugin.execute(
        db, llm, feature_name="src.x", context="FPT Telecom DS team — churn focus"
    )

    assert "ORG CONTEXT:" in captured["prompt"]
    assert "FPT Telecom DS team" in captured["prompt"]


def test_autodoc_empty_context_does_not_inject_section(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_generate_json(prompt: str, **kwargs: object) -> dict:
        captured["prompt"] = prompt
        return {
            "short_description": "x",
            "long_description": "y",
            "expected_range": "z",
            "potential_issues": "p",
            "suggested_tags": [],
        }

    llm = MagicMock()
    llm.generate_json.side_effect = fake_generate_json
    llm.model = "test"

    feature = _make_feature()
    db = MagicMock()
    db.get_feature_by_name.return_value = feature
    db.get_source_by_name.return_value = None

    monkeypatch.setattr(
        "featcat.catalog.context_builder.build_doc_context", lambda *a, **kw: []
    )

    plugin = AutodocPlugin()
    plugin.execute(db, llm, feature_name="src.x")
    assert "ORG CONTEXT:" not in captured["prompt"]
