"""Tests for the LLM layer: base, ollama, llamacpp."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from featcat.llm import create_llm
from featcat.llm.base import BaseLLM, LLMConnectionError, _extract_json
from featcat.llm.llamacpp import LlamaCppLLM
from featcat.llm.ollama import OllamaLLM

if TYPE_CHECKING:
    from collections.abc import Iterator

# --- Mock LLM for testing ---


class MockLLM(BaseLLM):
    """Mock LLM that returns preconfigured responses."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = responses or ['{"key": "value"}']
        self._call_count = 0

    def generate(self, prompt: str, system: str | None = None, temperature: float = 0.3, json_mode: bool = False) -> str:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]

    def stream(self, prompt: str, system: str | None = None, temperature: float = 0.3) -> Iterator[str]:
        response = self.generate(prompt, system, temperature)
        for word in response.split():
            yield word + " "

    def health_check(self) -> bool:
        return True


# --- JSON extraction tests ---


class TestExtractJson:
    def test_direct_json(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_markdown_fences(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_embedded_json(self):
        text = 'Here is the result:\n{"key": "value"}\nDone.'
        result = _extract_json(text)
        assert result == {"key": "value"}

    def test_invalid_json(self):
        result = _extract_json("not json at all")
        assert result is None

    def test_nested_json(self):
        text = '{"outer": {"inner": [1, 2]}}'
        result = _extract_json(text)
        assert result == {"outer": {"inner": [1, 2]}}


# --- BaseLLM generate_json tests ---


class TestGenerateJson:
    def test_success(self):
        llm = MockLLM(['{"status": "ok"}'])
        result = llm.generate_json("test")
        assert result == {"status": "ok"}

    def test_retry_on_failure(self):
        llm = MockLLM(["bad response", '{"status": "fixed"}'])
        result = llm.generate_json("test", max_retries=1)
        assert result == {"status": "fixed"}

    def test_failure_after_retries(self):
        llm = MockLLM(["bad", "still bad", "nope"])
        with pytest.raises(ValueError, match="Failed to parse JSON"):
            llm.generate_json("test", max_retries=2)

    def test_markdown_fenced_response(self):
        llm = MockLLM(['```json\n{"data": 42}\n```'])
        result = llm.generate_json("test")
        assert result == {"data": 42}


# --- Mock LLM stream test ---


class TestMockStream:
    def test_stream(self):
        llm = MockLLM(["hello world"])
        chunks = list(llm.stream("test"))
        assert len(chunks) == 2
        assert "hello" in chunks[0]


# --- Factory tests ---


class TestFactory:
    def test_create_ollama(self):
        llm = create_llm("ollama", model="test", base_url="http://localhost:11434")
        assert isinstance(llm, OllamaLLM)
        assert llm.model == "test"

    def test_create_llamacpp(self):
        llm = create_llm("llamacpp", base_url="http://localhost:8080")
        assert isinstance(llm, LlamaCppLLM)

    def test_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            create_llm("unknown")


# --- Ollama connection error test ---


class TestOllamaErrors:
    def test_health_check_unreachable(self):
        llm = OllamaLLM(base_url="http://localhost:99999")
        assert llm.health_check() is False

    def test_generate_connection_error(self):
        llm = OllamaLLM(base_url="http://localhost:99999")
        with pytest.raises(LLMConnectionError):
            llm.generate("test")
