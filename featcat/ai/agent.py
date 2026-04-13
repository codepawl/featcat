"""Catalog agent with native tool calling via llama.cpp."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .executor import ToolExecutor
from .tools import CATALOG_TOOLS

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from featcat.catalog.backend import CatalogBackend
    from featcat.llm.llamacpp import LlamaCppLLM

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3

SYSTEM_PROMPT = """\
You are featcat, a feature catalog assistant for FPT Telecom's Data Science team.
You help find, understand, compare, and evaluate features in the catalog.

Rules:
- Use tools to look up information. Do not guess feature details.
- For greetings or general questions, respond directly without tools.
- Match the user's language (Vietnamese or English).
- Be concise and actionable.
- When drift/quality issues found, explain severity and next steps."""


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
                for tc in tool_calls:
                    func = tc.get("function", tc)
                    tool_name = func.get("name", "")
                    raw_args = func.get("arguments", "{}")
                    tool_params = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                    yield {"type": "thinking", "content": f"Looking up: {tool_name}..."}
                    yield {"type": "tool_call", "name": tool_name, "params": tool_params}

                    tool_result = self.executor.execute(tool_name, tool_params)

                    yield {"type": "tool_result", "name": tool_name, "result": tool_result}

                    # Append to conversation for next round
                    messages.append({"role": "assistant", "content": None, "tool_calls": [tc]})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id", f"call_{_round}"),
                            "content": tool_result,
                        }
                    )
                continue  # next round — LLM will see tool results

            # No tool calls → final text response
            content = (result.get("content") or "").strip()
            if content:
                # Yield in chunks for streaming UX
                chunk_size = 20
                for i in range(0, len(content), chunk_size):
                    yield {"type": "token", "content": content[i : i + chunk_size]}

            yield {"type": "done"}
            return

        # Exceeded max rounds
        yield {"type": "token", "content": "Reached tool call limit. Try a more specific question."}
        yield {"type": "done"}
