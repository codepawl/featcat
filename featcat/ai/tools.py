"""Tool definitions for the catalog agent (OpenAI function-calling format)."""

from __future__ import annotations

CATALOG_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_features",
            "description": "Search the feature catalog by keyword. Returns matching features with stats.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or phrase"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_feature_detail",
            "description": "Get full metadata, statistics, and documentation for one feature.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string", "description": "Full feature name like source.column"},
                },
                "required": ["feature_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_drift_report",
            "description": "Get drift and quality alerts. Empty feature_name returns a summary of all alerts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string", "description": "Feature name, or empty string for all"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_features",
            "description": "Suggest existing and new features for an ML use case.",
            "parameters": {
                "type": "object",
                "properties": {
                    "use_case": {"type": "string", "description": "Description of the ML task or business problem"},
                },
                "required": ["use_case"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_features",
            "description": "Side-by-side statistics comparison of two or more features.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_names": {"type": "string", "description": "Comma-separated feature names to compare"},
                },
                "required": ["feature_names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_sources",
            "description": "List all registered data sources in the catalog.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]
