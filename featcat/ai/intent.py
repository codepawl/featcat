"""Intent classifier that routes user queries to a focused tool subset.

The catalog agent currently sends all 14 tool schemas (~1,408 tokens) on
every LLM call. On a 2B-param CPU model that's both a prompt-eval cost
(~13s per call at 65 tok/s) and an attention dilution problem — the model
sometimes picks the wrong tool when ~2k tokens of schemas compete.

This module classifies each user query with precompiled regex rules and
returns a tool subset (usually 1-4 tools). The full executor still holds
all 14 tool implementations; we just filter what's exposed in the prompt.

Pure-Python; no LLM call. Multi-intent supported (every matching rule
contributes its tool subset; the final selection is the union). Falls
back to a small versatile set when nothing matches.

See `audits/ai-chat-mvp-failure-analysis-2026-05-12.md` Section 3 (P0.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .tools import CATALOG_TOOLS


@dataclass(frozen=True)
class ToolSelection:
    """Result of intent classification for one query."""

    labels: tuple[str, ...]
    """All matching intent labels (empty when fallback fired)."""

    tools: tuple[str, ...]
    """Tool names to expose to the LLM, union of matched rules' subsets."""

    fallback: bool
    """True when no rule matched and DEFAULT_FALLBACK_TOOLS was used."""


# Each rule: (precompiled regex, tool subset, label).
# Rules are NOT mutually exclusive — every matching rule contributes its
# tool subset; the final selection is the union. The model still picks the
# right tool inside the subset.
#
# Ordering note: the regexes don't short-circuit on each other, but a few
# rules deliberately overlap (e.g. "duplicate" + "similar", "list" + others)
# so the LLM keeps related tools side-by-side in context.
_RULES: tuple[tuple[re.Pattern[str], tuple[str, ...], str], ...] = (
    # Count / aggregation. "có bao nhiêu features" / "how many".
    (
        re.compile(r"\b(có\s+bao\s+nhiêu|tổng\s+số|số\s+lượng|how\s+many|count|total)\b"),
        ("count_features", "catalog_summary"),
        "count",
    ),
    # Doc-status filter. Catches every phrasing of "without docs" / "chưa có doc".
    (
        re.compile(
            r"(chưa\s+có\s+(tài\s+liệu|doc)|không\s+có\s+(tài\s+liệu|doc)|"
            r"undocumented|without\s+docs?|missing\s+doc)"
        ),
        ("list_features", "count_features"),
        "doc_status",
    ),
    # Drift / health. "baseline" included so C2-style follow-ups
    # ("nó so với baseline gốc thì sao?") resolve correctly.
    (
        re.compile(
            r"\b(drift|biến\s+động|baseline|alert|cảnh\s+báo|critical|"
            r"warning|nghiêm\s+trọng|monitoring)\b"
        ),
        ("get_drift_report",),
        "drift",
    ),
    # Group lookup.
    (
        re.compile(r"\b(group|nhóm)\b"),
        ("get_group", "list_groups"),
        "group",
    ),
    # Per-source breakdown ("source nào nhiều feature nhất").
    (
        re.compile(r"(source\s+nào|nguồn\s+nào|which\s+source|per\s+source|breakdown.*source)"),
        ("features_by_source", "list_sources"),
        "source_breakdown",
    ),
    # Source listing.
    (
        re.compile(r"(liệt\s+kê.*(source|nguồn)|list.*sources?|all\s+sources)"),
        ("list_sources",),
        "source_list",
    ),
    # Single-feature detail.
    (
        re.compile(r"(chi\s+tiết|thông\s+tin.*feature|details?\s+about|info\s+(about|on))"),
        ("get_feature_detail",),
        "detail",
    ),
    # Comparison.
    (
        re.compile(r"\b(so\s+sánh|khác\s+gì|chúng\s+khác|compare|difference\s+between)\b"),
        ("compare_features",),
        "compare",
    ),
    # Catalog-wide duplicates.
    (
        re.compile(r"(duplicate|trùng\s+lặp|nghi\s+ngờ.*(duplicate|trùng)|find\s+dupes?)"),
        ("find_duplicate_pairs", "find_similar_features"),
        "duplicate",
    ),
    # Per-reference similar features — distinct from catalog-wide dup scan.
    (
        re.compile(r"(giống\s+(feature\s+)?\S+|similar\s+to\s+\S+|features?\s+like\s+\S+)"),
        ("find_similar_features",),
        "similar",
    ),
    # Use-case recommendation.
    (
        re.compile(r"\b(gợi\s+ý|recommend|suggest|nên\s+dùng|use\s+case|model.*dự\s+đoán)\b"),
        ("suggest_features",),
        "recommend",
    ),
    # Catalog overview / summary.
    (
        re.compile(r"\b(tóm\s+tắt|tổng\s+quan|summary|overview|health\s+summary|tình\s+trạng)\b"),
        ("catalog_summary",),
        "summary",
    ),
    # Generic feature list.
    (
        re.compile(r"(liệt\s+kê.*features?|danh\s+sách.*features?|list.*features?|show.*features?)"),
        ("list_features",),
        "list",
    ),
    # Keyword / topic search.
    (
        re.compile(r"(tìm.*(feature|về|liên\s+quan)|search.*features?|find.*features?\s+about)"),
        ("search_features",),
        "search",
    ),
)


# Versatile fallback for unmatched queries. Covers the most generic shapes
# (search, list, detail, summary) without exposing all 14 schemas.
DEFAULT_FALLBACK_TOOLS: tuple[str, ...] = (
    "search_features",
    "list_features",
    "get_feature_detail",
    "catalog_summary",
)


def classify_intent(query: str) -> ToolSelection:
    """Return the tool subset for `query`.

    Every matching rule contributes; the union of their tool names is
    returned. Falls back to ``DEFAULT_FALLBACK_TOOLS`` when no rule matches.
    """
    q = query.lower()
    labels: list[str] = []
    tools: list[str] = []
    for pattern, rule_tools, label in _RULES:
        if pattern.search(q):
            labels.append(label)
            for t in rule_tools:
                if t not in tools:
                    tools.append(t)
    if not labels:
        return ToolSelection(labels=(), tools=DEFAULT_FALLBACK_TOOLS, fallback=True)
    return ToolSelection(labels=tuple(labels), tools=tuple(tools), fallback=False)


_TOOL_BY_NAME: dict[str, dict] = {t["function"]["name"]: t for t in CATALOG_TOOLS}


def select_tool_schemas(query: str) -> tuple[list[dict], ToolSelection]:
    """Return ``(filtered_tool_schemas, selection)`` for ``query``.

    The schemas are a subset of ``CATALOG_TOOLS`` preserving the original
    dict shape so they pass through to llama.cpp's ``tools`` payload.
    """
    selection = classify_intent(query)
    schemas = [_TOOL_BY_NAME[name] for name in selection.tools if name in _TOOL_BY_NAME]
    return schemas, selection
