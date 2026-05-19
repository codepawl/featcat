"""Tool definitions for the catalog agent (OpenAI function-calling format)."""

from __future__ import annotations

CATALOG_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "search_features",
            "description": (
                "Hybrid lexical + semantic search across feature names, descriptions, tags, "
                "and column names. Accepts free-form Vietnamese or English queries — does NOT "
                "require exact match, partial phrases work. Examples: 'tiền', 'billing', "
                "'doanh thu', 'churn risk', 'cpu usage'. Returns the top matches ranked by "
                "combined relevance. For structured filters (by source / has_doc / dtype) "
                "use list_features instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-form query in any language; partial phrases are fine.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_features",
            "description": (
                "List features matching structured filters. Use for queries like "
                "'features without docs' (has_doc=false), 'features in source X' (source='X'), "
                "'float64 features in user_data' (source='user_data', dtype='float64'). "
                "Returns up to `limit` features (default 20, max 50)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source name (e.g. 'device_logs')"},
                    "has_doc": {
                        "type": "boolean",
                        "description": "true = only documented features; false = only undocumented",
                    },
                    "dtype": {
                        "type": "string",
                        "description": "Filter by dtype, e.g. 'float64', 'int64', 'string', 'bool'",
                    },
                    "name_contains": {
                        "type": "string",
                        "description": "Substring of feature name to match",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (1-50). Defaults to 20.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "count_features",
            "description": (
                "Count features matching filters. Use for 'how many' / 'có bao nhiêu' questions. "
                "Cheaper than list_features when only the count is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "has_doc": {"type": "boolean"},
                    "dtype": {"type": "string"},
                    "name_contains": {"type": "string"},
                },
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
            "description": (
                "Get latest drift / quality alerts from monitoring history. "
                "Empty feature_name returns a summary across the catalog. "
                "Reads stored checks (cheap); does NOT recompute baselines."
            ),
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
            "description": (
                "Recommend features for a described ML use case (e.g. 'churn prediction'). "
                "Uses TF-IDF over the catalog and an LLM rerank when available."
            ),
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
    {
        "type": "function",
        "function": {
            "name": "catalog_summary",
            "description": (
                "High-level catalog snapshot: total features, sources, groups, doc coverage, "
                "drift severity counts. Use for 'tổng quan catalog' / 'health overview' queries."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "features_by_source",
            "description": (
                "Per-source feature counts and doc coverage. Use for 'source nào có nhiều feature nhất' "
                "or 'breakdown by source' queries."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_groups",
            "description": "List all feature groups with member counts and owner.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_group",
            "description": (
                "Get one feature group's details: description, owner, members. "
                "Use for 'group X có những feature nào' queries."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Group name"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_features",
            "description": (
                "Find features similar to ONE reference feature by name. Use for 'features similar "
                "to X', 'gì giống X'. Requires feature_name. For catalog-wide duplicate scans, use "
                "find_duplicate_pairs instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {"type": "string", "description": "Reference feature name"},
                    "top_k": {"type": "integer", "description": "Max results (1-20, default 5)"},
                },
                "required": ["feature_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_duplicate_pairs",
            "description": (
                "Find feature pairs that look like duplicates across the catalog. Use for "
                "'có feature nào nghi ngờ duplicate', 'tìm duplicate trong source X', or 'tìm "
                "duplicate với threshold N'. Different from find_similar_features (which is "
                "per-reference-feature)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "description": "Minimum similarity score (0.4-0.95). Default 0.7.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Optional: restrict to one source name (e.g. 'device_logs').",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max pairs to return (1-50). Default 20.",
                    },
                },
            },
        },
    },
]
