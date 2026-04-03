# ruff: noqa: E501
"""Prompt templates for all AI plugins."""

from __future__ import annotations

# =============================================================================
# Feature Discovery
# =============================================================================

DISCOVERY_SYSTEM = """\
You are an expert data scientist working with a feature catalog.
Your task is to analyze a feature catalog and suggest relevant features for a given use case.

Think step-by-step:
1. Understand the use case requirements
2. Review each available feature and assess its relevance
3. Identify gaps — features that would help but don't exist yet
4. Suggest new features that could be derived from existing data sources

Always return valid JSON. Do not include markdown fences or extra text outside the JSON."""

DISCOVERY_PROMPT = """\
USE CASE: {use_case}

AVAILABLE FEATURES:
{feature_summary}

DATA SOURCES:
{source_schemas}

Based on the feature catalog above, return a JSON object with this structure:
{{
  "existing_features": [
    {{"name": "feature_name", "relevance": 0.9, "reason": "why this feature is relevant"}}
  ],
  "new_feature_suggestions": [
    {{"name": "suggested_name", "source": "data_source_name", "column_expression": "how to compute", "reason": "why this would help"}}
  ],
  "summary": "overall feature engineering strategy for this use case"
}}

Example of a good response:
{{
  "existing_features": [
    {{"name": "user_behavior_30d.session_count", "relevance": 0.95, "reason": "Session frequency is a strong churn predictor"}},
    {{"name": "user_behavior_30d.complaint_count", "relevance": 0.90, "reason": "Complaints directly correlate with churn intent"}}
  ],
  "new_feature_suggestions": [
    {{"name": "session_trend_7d", "source": "user_behavior_30d", "column_expression": "slope of session_count over last 7 days", "reason": "Declining trend captures early churn signals"}}
  ],
  "summary": "Focus on behavioral engagement features and their trends over time"
}}

Return ONLY the JSON object."""

# =============================================================================
# Auto Documentation
# =============================================================================

AUTODOC_SYSTEM = """\
You are a data documentation specialist for a telecom data science team.
Generate clear, accurate documentation for data features based on their metadata and statistics.
Documentation should be helpful for data scientists who need to understand and use these features.

Always return valid JSON. No markdown fences or extra text."""

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
Generate documentation for the following features from source "{source_name}" ({source_path}):

{features_text}

For EACH feature, return a JSON object with this structure. Return a JSON array of objects:
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
You are a data quality expert analyzing drift reports for a telecom data science team.
Explain detected issues in practical terms and suggest actionable next steps.

Always return valid JSON."""

MONITORING_ANALYSIS_PROMPT = """\
A data quality check detected the following issues:

{drift_report}

Feature context:
{feature_context}

Analyze each issue and return a JSON object:
{{
  "analyses": [
    {{
      "feature": "feature_name",
      "likely_cause": "most probable reason for the drift",
      "severity_assessment": "how urgent is this — low/medium/high",
      "recommended_actions": ["action 1", "action 2"],
      "should_retrain": true/false
    }}
  ],
  "overall_assessment": "brief summary of data quality status"
}}"""

# =============================================================================
# Natural Language Query
# =============================================================================

NL_QUERY_SYSTEM = """\
You are a feature catalog search expert for a data science team.
Given a user's natural language query, search and rank features from the catalog.
Respond in the same language as the user's query (English or Vietnamese).
Feature names always stay in English.

Always return valid JSON."""

NL_QUERY_PROMPT = """\
FEATURE CATALOG:
{feature_summary}

USER QUERY: {query}

Search the catalog and return a JSON object:
{{
  "results": [
    {{"feature": "feature_name", "score": 0.95, "reason": "why this matches the query"}}
  ],
  "interpretation": "how you understood the query",
  "follow_up": "a suggested follow-up query that might also be useful"
}}

Rank results by relevance score (0.0 to 1.0). Include only features with score >= 0.3.
Return ONLY the JSON object."""

NL_QUERY_SYSTEM_VI = """\
You are a feature catalog search expert for a data science team.
Given a user's query in Vietnamese, search and rank features from the catalog.
Respond in Vietnamese. Feature names always stay in English.

Always return valid JSON."""
