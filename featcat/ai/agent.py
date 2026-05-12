"""Catalog agent with native tool calling via llama.cpp."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from starlette.concurrency import run_in_threadpool

from .executor import ToolExecutor
from .tools import CATALOG_TOOLS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from featcat.catalog.backend import CatalogBackend
    from featcat.llm.llamacpp import LlamaCppLLM

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 2

SYSTEM_PROMPT = """\
You are featcat, a feature catalog assistant for FPT Telecom's Data Science team.

IMPORTANT: When the user asks about features, data quality, groups, sources, or use cases, \
you MUST call the appropriate tool immediately. Do NOT describe tools or ask what the user \
wants — just use them.

Tool picking guide:
- Keyword/topic search ("features về churn"): search_features(query=...)
- Structured filter ("chưa có doc", "trong source X", "dtype float64"): \
list_features(has_doc=False, source=..., dtype=...)
- Counting ("có bao nhiêu feature ..."): count_features(...)
- Single feature deep dive ("chi tiết X", "stats của X"): get_feature_detail(feature_name=...)
- Comparison: compare_features(feature_names="a,b")
- Drift / quality alerts ("đang drift", "data quality"): get_drift_report()
- Use-case recommendation ("gợi ý feature cho churn model"): suggest_features(use_case=...)
- Sources list: list_sources()
- Per-source breakdown ("source nào nhiều feature nhất"): features_by_source()
- Catalog overview ("tổng quan catalog", "health summary"): catalog_summary()
- Groups list: list_groups()
- One group's members ("group X có gì"): get_group(name=...)
- Similar features (per reference feature): find_similar_features(feature_name=..., top_k=5)
- Catalog-wide duplicates ("có feature nào nghi ngờ duplicate", "tìm duplicate \
trong source X", "duplicate với threshold N"): \
find_duplicate_pairs(threshold=..., source=...)
- Greeting ("xin chào"): respond directly, no tool needed

Common workflows:
- "Feature nào chưa có tài liệu?" → list_features(has_doc=False)
- "Có bao nhiêu feature chưa có doc?" → count_features(has_doc=False)
- "Tổng quan catalog" → catalog_summary()
- "Group churn_features có gì" → get_group(name="churn_features")
- "Source nào nhiều feature nhất" → features_by_source()

Rules:
- Act first, explain after. Call tools proactively.
- Use the minimum number of tool calls needed. After getting results, summarize them directly \
unless the user asks for more detail. Do NOT chain all tools in one turn.
- If a tool returns an empty list or "not found", say so plainly — do NOT invent features.
- Match the user's language (Vietnamese or English).
- Be concise. No filler.
- After getting tool results, summarize with actionable insights."""

_SUMMARY_PROMPT = (
    "Based on the tool results above, give a concise answer to my original question. "
    "Do NOT call any tools. Do NOT output XML tags. Just answer in plain text. "
    "Trả lời ngắn gọn, dưới 4 câu. Tập trung vào điểm chính."
)

# Hard cap for the forced-summary LLM call. The first agent-loop call keeps the
# 2048 default so tool-arg generation isn't truncated; the summary doesn't need
# more than a few sentences and caps the worst-case latency.
_SUMMARY_MAX_TOKENS = 600

# Tools whose executor output is already user-readable. When every tool call
# in a round is in this set (or list_features below the size threshold), the
# agent streams the tool result directly to the user and skips the second LLM
# call. Cuts ~30-60s off fact-lookup queries on a 2B model. See audit
# `audits/ai-chat-mvp-failure-analysis-2026-05-12.md`.
SELF_EXPLANATORY_TOOLS: frozenset[str] = frozenset(
    {
        "list_sources",
        "get_feature_detail",
        "get_group",
        "catalog_summary",
        "features_by_source",
        "list_groups",
        "count_features",
    }
)

# list_features is self-explanatory only when the result is short enough to be
# meaningful without prose framing.
_LIST_FEATURES_SHORT_THRESHOLD = 20

# Vietnamese intros rotated for self-explanatory tool replies. Picked by
# message count so consecutive queries vary without RNG (deterministic for
# tests).
_VI_RESULT_INTROS: tuple[str, ...] = (
    "Đây là kết quả:",
    "Đây là thông tin cho bạn:",
    "Kết quả:",
)


def _list_features_short(result: str) -> bool:
    """Parse the 'Showing N of M matching features:' line to gate self-explanation.

    Returns True when list_features returned ≤ _LIST_FEATURES_SHORT_THRESHOLD
    rows so the raw output is digestible without prose framing.
    """
    first_line = result.split("\n", 1)[0] if result else ""
    m = re.match(r"Showing\s+(\d+)\s+of\s+\d+\s+matching features:", first_line)
    if not m:
        return False
    return int(m.group(1)) <= _LIST_FEATURES_SHORT_THRESHOLD


def _all_self_explanatory(executed: list[tuple[str, str]]) -> bool:
    """True when every (tool_name, result) pair is in the self-explanatory set."""
    if not executed:
        return False
    for name, result in executed:
        if name in SELF_EXPLANATORY_TOOLS:
            continue
        if name == "list_features" and _list_features_short(result):
            continue
        return False
    return True


_TOOL_TAG_RE = re.compile(
    r"</?tool_call[^>]*>|</?function[^>]*>|</?parameter[^>]*>|\{\"name\":\s*\"[a-z_]+\"",
    re.DOTALL,
)


def _clean_content(text: str) -> str:
    """Strip leaked tool-call XML/JSON tags from model output."""
    cleaned = _TOOL_TAG_RE.sub("", text).strip()
    # Collapse multiple blank lines left by stripping
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


class CatalogAgent:
    """Agentic chat with native tool calling."""

    def __init__(self, llm: LlamaCppLLM, backend: CatalogBackend) -> None:
        self.llm = llm
        self.executor = ToolExecutor(backend, llm)

    async def chat(self, user_message: str, history: list[dict] | None = None) -> AsyncIterator[dict[str, Any]]:
        """Process a user message through the agentic loop.

        Yields SSE-compatible event dicts:
            {"type": "thinking", "content": "..."}
            {"type": "tool_call", "name": "...", "params": {...}}
            {"type": "tool_result", "name": "...", "result": "..."}
            {"type": "token", "content": "..."}
            {"type": "done"}
        """
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_message})

        tool_call_history: set[str] = set()

        for _round in range(MAX_TOOL_ROUNDS):
            try:
                result = await run_in_threadpool(self.llm.chat, messages, tools=CATALOG_TOOLS)
            except Exception as e:
                logger.error("LLM chat failed: %s", e)
                yield {"type": "token", "content": f"LLM error: {e}"}
                yield {"type": "done"}
                return

            tool_calls = result.get("tool_calls")
            if tool_calls:
                duplicate = False
                executed: list[tuple[str, str]] = []
                for tc in tool_calls:
                    func = tc.get("function", tc)
                    tool_name = func.get("name", "")
                    raw_args = func.get("arguments", "{}")
                    tool_params = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                    call_key = f"{tool_name}:{json.dumps(tool_params, sort_keys=True)}"
                    if call_key in tool_call_history:
                        duplicate = True
                        break
                    tool_call_history.add(call_key)

                    yield {"type": "tool_start", "tool": tool_name}
                    yield {"type": "tool_call", "name": tool_name, "params": tool_params}

                    tool_result = self.executor.execute(tool_name, tool_params)
                    executed.append((tool_name, tool_result))

                    yield {"type": "tool_result", "name": tool_name, "result": tool_result}

                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", f"call_{_round}"),
                            "content": tool_result,
                        }
                    )

                if duplicate:
                    break  # Fall through to forced summary

                # If every tool in this round is self-explanatory, stream the
                # result directly with a VI intro and skip the second LLM call.
                # Saves a full generation pass (~30-60s on Gemma 4 E2B CPU).
                if _all_self_explanatory(executed):
                    intro = _VI_RESULT_INTROS[len(messages) % len(_VI_RESULT_INTROS)]
                    direct = intro + "\n\n" + "\n\n".join(r for _n, r in executed)
                    chunk_size = 20
                    for i in range(0, len(direct), chunk_size):
                        yield {"type": "token", "content": direct[i : i + chunk_size]}
                    yield {"type": "done"}
                    return

                continue  # Next round

            # No tool calls → final text response
            content = _clean_content(result.get("content") or "")
            if content:
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield {"type": "token", "content": content[i : i + chunk_size]}

            yield {"type": "done"}
            return

        # Exceeded rounds or duplicate detected — force a text summary
        async for event in self._force_summary(messages):
            yield event

    async def _force_summary(self, messages: list[dict]) -> AsyncIterator[dict[str, Any]]:
        """Make a final LLM call without tools to summarize results."""
        messages.append({"role": "user", "content": _SUMMARY_PROMPT})
        try:
            result = await run_in_threadpool(self.llm.chat, messages, temperature=0.3, max_tokens=_SUMMARY_MAX_TOKENS)
            content = _clean_content(result.get("content") or "")
            if content:
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield {"type": "token", "content": content[i : i + chunk_size]}
        except Exception as e:
            logger.error("Final summary failed: %s", e)
            yield {"type": "token", "content": "Could not generate summary. Try a more specific question."}
        yield {"type": "done"}
