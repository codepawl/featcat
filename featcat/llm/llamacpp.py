"""llama.cpp server LLM backend (OpenAI-compatible API)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import BaseLLM, LLMConnectionError, LLMTimeoutError, strip_thinking_tags

if TYPE_CHECKING:
    from collections.abc import Iterator


class LlamaCppLLM(BaseLLM):
    """LLM backend using llama.cpp server's OpenAI-compatible /v1/chat/completions."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        model: str = "qwen3.5-0.8b",
        timeout: int = 300,
        **kwargs,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def _build_messages(self, prompt: str, system: str | None = None) -> list[dict]:
        """Build chat messages array from prompt and optional system message."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        tools: list[dict] | None = None,
    ) -> dict:
        """Send chat completion with optional tool calling.

        Returns dict with: content, tool_calls, finish_reason
        """
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "max_tokens": 2048,
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            raise LLMConnectionError(
                f"Cannot connect to llama.cpp server at {self.base_url}. Is the server running?\nError: {e}"
            ) from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"llama.cpp request timed out after {self.timeout}s") from e

        choice = data["choices"][0]
        message = choice["message"]
        return {
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls"),
            "finish_reason": choice.get("finish_reason", "stop"),
        }

    def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Stream chat completion tokens from message history."""
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            "max_tokens": 2048,
        }

        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if not decoded or not decoded.startswith("data: "):
                        continue
                    data_str = decoded[6:]
                    if data_str == "[DONE]":
                        return
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    token = delta.get("content", "")
                    if token:
                        yield token
        except URLError as e:
            raise LLMConnectionError(
                f"Cannot connect to llama.cpp server at {self.base_url}. Is the server running?\nError: {e}"
            ) from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"llama.cpp request timed out after {self.timeout}s") from e

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
    ) -> str:
        """Generate a complete response from llama.cpp server."""
        messages = self._build_messages(prompt, system)
        result = self.chat(messages, temperature=temperature)
        content = result["content"] or ""
        return strip_thinking_tags(content)

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
        """Stream response chunks from llama.cpp server."""
        messages = self._build_messages(prompt, system)
        yield from self.stream_chat(messages, temperature=temperature)

    def health_check(self) -> bool:
        """Check if llama.cpp server is running."""
        try:
            req = Request(f"{self.base_url}/health", method="GET")
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False
