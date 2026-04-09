"""Tests for the LLM response cache."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from featcat.llm.base import BaseLLM
from featcat.llm.cached import CachedLLM
from featcat.utils.cache import ResponseCache

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


class CountingLLM(BaseLLM):
    """LLM that counts calls and returns a fixed response."""

    def __init__(self, response: str = "test response") -> None:
        self.call_count = 0
        self._response = response

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
    ) -> str:
        self.call_count += 1
        return self._response

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
        yield self._response

    def health_check(self) -> bool:
        return True


@pytest.fixture()
def cache(tmp_path: Path) -> ResponseCache:
    c = ResponseCache(str(tmp_path / "test.db"))
    yield c
    c.close()


class TestResponseCache:
    def test_put_and_get(self, cache: ResponseCache):
        cache.put("prompt1", "response1", ttl_seconds=3600)
        assert cache.get("prompt1") == "response1"

    def test_miss(self, cache: ResponseCache):
        assert cache.get("nonexistent") is None

    def test_expired(self, cache: ResponseCache):
        cache.put("prompt1", "response1", ttl_seconds=0)
        # TTL=0 means already expired
        time.sleep(0.1)
        assert cache.get("prompt1") is None

    def test_system_prompt_affects_key(self, cache: ResponseCache):
        cache.put("prompt1", "resp_a", ttl_seconds=3600, system="system_a")
        cache.put("prompt1", "resp_b", ttl_seconds=3600, system="system_b")
        assert cache.get("prompt1", system="system_a") == "resp_a"
        assert cache.get("prompt1", system="system_b") == "resp_b"

    def test_clear(self, cache: ResponseCache):
        cache.put("a", "1", 3600)
        cache.put("b", "2", 3600)
        count = cache.clear()
        assert count == 2
        assert cache.get("a") is None

    def test_clear_expired(self, cache: ResponseCache):
        cache.put("active", "1", ttl_seconds=3600)
        cache.put("expired", "2", ttl_seconds=0)
        time.sleep(0.1)
        removed = cache.clear_expired()
        assert removed == 1
        assert cache.get("active") == "1"

    def test_stats(self, cache: ResponseCache):
        cache.put("a", "1", 3600)
        cache.put("b", "2", 0)
        time.sleep(0.1)
        s = cache.stats()
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["expired"] == 1


class TestCachedLLM:
    def test_caches_response(self, cache: ResponseCache):
        inner = CountingLLM("hello")
        llm = CachedLLM(inner, cache, default_ttl=3600)

        r1 = llm.generate("test prompt")
        r2 = llm.generate("test prompt")

        assert r1 == "hello"
        assert r2 == "hello"
        assert inner.call_count == 1  # Only called once, second was cached

    def test_different_prompts_not_cached(self, cache: ResponseCache):
        inner = CountingLLM("hello")
        llm = CachedLLM(inner, cache, default_ttl=3600)

        llm.generate("prompt a")
        llm.generate("prompt b")

        assert inner.call_count == 2

    def test_stream_not_cached(self, cache: ResponseCache):
        inner = CountingLLM("hello")
        llm = CachedLLM(inner, cache, default_ttl=3600)

        chunks = list(llm.stream("test"))
        assert chunks == ["hello"]

    def test_health_check_passthrough(self, cache: ResponseCache):
        inner = CountingLLM()
        llm = CachedLLM(inner, cache)
        assert llm.health_check() is True

    def test_model_attribute(self, cache: ResponseCache):
        inner = CountingLLM()
        inner.model = "test-model"
        llm = CachedLLM(inner, cache)
        assert llm.model == "test-model"
