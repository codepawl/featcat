"""Fallback agent — no LLM, keyword search only."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from featcat.catalog.backend import CatalogBackend

_GREETINGS = frozenset(["hello", "hi", "hey", "xin chào", "chào", "hallo", "yo"])


class FallbackAgent:
    """Responds without an LLM using keyword search."""

    def __init__(self, backend: CatalogBackend) -> None:
        self.backend = backend

    async def chat(self, user_message: str, history: list[dict] | None = None) -> AsyncIterator[dict[str, Any]]:
        query = user_message.lower().strip()

        if any(query.startswith(g) for g in _GREETINGS):
            yield {
                "type": "token",
                "content": "Chào bạn! Mình là featcat. Hỏi về features trong catalog nhé. (LLM offline)",
            }
            yield {"type": "done"}
            return

        features = self.backend.search_features(user_message)
        if features:
            lines = ["Kết quả keyword search (LLM offline):\n"]
            for f in features[:10]:
                desc = f.description or ""
                lines.append(f"- **{f.name}** ({f.dtype}): {desc}")
            yield {"type": "token", "content": "\n".join(lines)}
        else:
            msg = f"Không tìm thấy features cho '{user_message}'. Thử keyword khác? (LLM offline)"
            yield {"type": "token", "content": msg}

        yield {"type": "done"}
