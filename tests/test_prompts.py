"""Tests for prompt template structure (independent of the LLM)."""

from __future__ import annotations

from featcat.utils.prompts import AUTODOC_PROMPT_SINGLE


def test_autodoc_prompt_has_context_section_placeholder() -> None:
    """The autodoc prompt must accept a {context_section} slot so the CLI
    --context flag can inject org context without code changes."""
    assert "{context_section}" in AUTODOC_PROMPT_SINGLE


def test_autodoc_prompt_formats_with_all_required_placeholders() -> None:
    formatted = AUTODOC_PROMPT_SINGLE.format(
        feature_name="src.x",
        column_name="x",
        dtype="float64",
        source_name="src",
        source_path="/data/src.parquet",
        tags="(none)",
        stats_text="",
        hints_section="",
        same_source_section="",
        cross_source_section="",
        context_section="",
    )
    assert "src.x" in formatted
    assert "ORG CONTEXT:" not in formatted  # empty section, no header leaked


def test_autodoc_prompt_includes_context_when_provided() -> None:
    formatted = AUTODOC_PROMPT_SINGLE.format(
        feature_name="src.x",
        column_name="x",
        dtype="float64",
        source_name="src",
        source_path="/data/src.parquet",
        tags="(none)",
        stats_text="",
        hints_section="",
        same_source_section="",
        cross_source_section="",
        context_section="\nORG CONTEXT:\nFPT Telecom DS team\n",
    )
    assert "ORG CONTEXT:" in formatted
    assert "FPT Telecom DS team" in formatted
