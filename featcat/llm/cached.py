"""Caching wrapper for LLM backends."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import BaseLLM

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..utils.cache import ResponseCache


class CachedLLM(BaseLLM):
    """Wraps another LLM backend with response caching.

    Only caches non-streaming generate() calls.
    """

    def __init__(self, inner: BaseLLM, cache: ResponseCache, default_ttl: int = 3600) -> None:
        self.inner = inner
        self.cache = cache
        self.default_ttl = default_ttl

    # Forward model attribute for autodoc's _save_doc
    @property
    def model(self) -> str:
        return getattr(self.inner, "model", "unknown")

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
        ttl: int | None = None,
    ) -> str:
        """Generate with cache lookup."""
        cached = self.cache.get(prompt, system)
        if cached is not None:
            return cached

        response = self.inner.generate(prompt, system=system, temperature=temperature, json_mode=json_mode, think=think)
        self.cache.put(prompt, response, ttl or self.default_ttl, system=system)
        return response

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
        """Stream is not cached — passes through directly."""
        yield from self.inner.stream(prompt, system=system, temperature=temperature, think=think)

    def health_check(self) -> bool:
        return self.inner.health_check()
