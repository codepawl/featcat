"""Catalog agent with native tool calling via llama.cpp."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

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

IMPORTANT: When the user asks about features, data quality, or use cases, you MUST call \
the appropriate tool immediately. Do NOT describe tools or ask what the user wants — just use them.

Examples:
- "features liên quan đến churn" → call search_features(query="churn")
- "chi tiết cpu_usage" → call get_feature_detail(feature_name="device_performance.cpu_usage")
- "so sánh cpu và memory" → call compare_features(feature_names="device_performance.cpu_usage,device_performance.memory_usage")
- "data quality" → call get_drift_report()
- "xin chào" → respond directly, no tool needed

Rules:
- Act first, explain after. Call tools proactively.
- Use the minimum number of tool calls needed. After search results, summarize them directly unless the user asks for more detail. Do NOT chain all tools in one turn.
- Match the user's language (Vietnamese or English).
- Be concise. No filler.
- After getting tool results, summarize with actionable insights."""

_SUMMARY_PROMPT = (
    "Based on the tool results above, give a concise answer to my original question. "
    "Do NOT call any tools. Do NOT output XML tags. Just answer in plain text."
)

_TOOL_TAG_RE = re.compile(r"</?tool_call[^>]*>|</?function[^>]*>|</?parameter[^>]*>|\{\"name\":\s*\"[a-z_]+\"", re.DOTALL)


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
                result = self.llm.chat(messages, tools=CATALOG_TOOLS)
            except Exception as e:
                logger.error("LLM chat failed: %s", e)
                yield {"type": "token", "content": f"LLM error: {e}"}
                yield {"type": "done"}
                return

            tool_calls = result.get("tool_calls")
            if tool_calls:
                duplicate = False
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

                    yield {"type": "thinking", "content": f"Looking up: {tool_name}..."}
                    yield {"type": "tool_call", "name": tool_name, "params": tool_params}

                    tool_result = self.executor.execute(tool_name, tool_params)

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
                continue  # Next round

            # No tool calls → final text response
            content = _clean_content((result.get("content") or ""))
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
            result = self.llm.chat(messages, temperature=0.3)
            content = _clean_content((result.get("content") or ""))
            if content:
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield {"type": "token", "content": content[i : i + chunk_size]}
        except Exception as e:
            logger.error("Final summary failed: %s", e)
            yield {"type": "token", "content": "Could not generate summary. Try a more specific question."}
        yield {"type": "done"}
