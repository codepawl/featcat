# ruff: noqa: E501
"""Prompt templates for all AI plugins.

Optimized for small models (LFM 2.5, 1.2B params):
- Short system prompts (role + output format only)
- One compact example max
- Explicit "Output ONLY valid JSON" instruction
"""

from __future__ import annotations

# =============================================================================
# Feature Discovery
# =============================================================================

DISCOVERY_SYSTEM = """\
You are a data scientist analyzing a feature catalog. Suggest relevant features for a use case.
Output ONLY valid JSON, no explanation before or after."""

DISCOVERY_PROMPT = """\
USE CASE: {use_case}

AVAILABLE FEATURES:
{feature_summary}

DATA SOURCES:
{source_schemas}

Return a JSON object:
{{
  "existing_features": [
    {{"name": "feature_name", "relevance": 0.9, "reason": "why relevant"}}
  ],
  "new_feature_suggestions": [
    {{"name": "suggested_name", "source": "data_source_name", "column_expression": "how to compute", "reason": "why helpful"}}
  ],
  "summary": "feature engineering strategy for this use case"
}}

Return ONLY the JSON object."""

# =============================================================================
# Auto Documentation
# =============================================================================

AUTODOC_SYSTEM = """\
You are a data documentation specialist. Generate clear, accurate documentation for data features.
Output ONLY valid JSON, no explanation before or after."""

AUTODOC_PROMPT_SINGLE = """\
Generate documentation for this feature:

Feature: {feature_name}
Column: {column_name}
Data Type: {dtype}
Source: {source_name} ({source_path})
Tags: {tags}
Statistics:
{stats_text}

Other columns in the same source: {sibling_columns}

Return a JSON object:
{{
  "short_description": "one concise sentence describing the feature",
  "long_description": "2-3 sentences with more detail about meaning, usage, and context",
  "expected_range": "reasonable value range (e.g. '0-100 for percentage', '>= 0 for counts')",
  "potential_issues": "common data quality issues to watch for",
  "suggested_tags": ["tag1", "tag2"]
}}"""

AUTODOC_PROMPT_BATCH = """\
Generate documentation for features from source "{source_name}" ({source_path}):

{features_text}

For EACH feature, return a JSON array:
[
  {{
    "feature_name": "the feature name",
    "short_description": "one concise sentence",
    "long_description": "2-3 sentences with detail",
    "expected_range": "reasonable value range",
    "potential_issues": "data quality issues to watch for",
    "suggested_tags": ["tag1", "tag2"]
  }}
]

Return ONLY the JSON array."""

# =============================================================================
# Quality Monitoring - LLM Analysis
# =============================================================================

MONITORING_SYSTEM = """\
You are a data quality expert. Analyze drift reports and suggest actionable next steps.
Output ONLY valid JSON, no explanation before or after."""

MONITORING_ANALYSIS_PROMPT = """\
Data quality issues detected:

{drift_report}

Feature context:
{feature_context}

Return a JSON object:
{{
  "analyses": [
    {{
      "feature": "feature_name",
      "likely_cause": "most probable reason for the drift",
      "severity_assessment": "low/medium/high",
      "recommended_actions": ["action 1", "action 2"],
      "should_retrain": true
    }}
  ],
  "overall_assessment": "brief summary of data quality status"
}}"""

# =============================================================================
# Natural Language Query
# =============================================================================

NL_QUERY_SYSTEM = """\
You are a feature catalog search expert. Rank features by relevance to the user's query.
Respond in the same language as the query. Feature names stay in English.
Output ONLY valid JSON, no explanation before or after."""

NL_QUERY_PROMPT = """\
FEATURE CATALOG:
{feature_summary}

USER QUERY: {query}

Search the catalog above. Return a JSON object with these fields:
- "results": array of objects, each with "feature" (exact feature name from catalog), "score" (0.0 to 1.0), "reason" (short explanation)
- "interpretation": how you understood the query
- "follow_up": a suggested follow-up query or null

Rules: max 5 results, only features with score >= 0.3, return ONLY valid JSON, no markdown fences."""

# NL_QUERY_SYSTEM_VI was removed — use localize_system_prompt() from utils.lang instead.
