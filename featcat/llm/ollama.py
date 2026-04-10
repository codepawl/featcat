"""Ollama LLM backend (HTTP API at localhost:11434)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import BaseLLM, LLMConnectionError, LLMTimeoutError, strip_thinking_tags

if TYPE_CHECKING:
    from collections.abc import Iterator


class OllamaLLM(BaseLLM):
    """LLM backend using Ollama's /api/chat endpoint."""

    def __init__(
        self,
        model: str = "qwen3.5:0.8b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def _build_messages(self, prompt: str, system: str | None = None) -> list[dict]:
        """Build chat messages array from prompt and optional system message."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
    ) -> str:
        """Generate a complete response from Ollama using /api/chat."""
        payload: dict = {
            "model": self.model,
            "messages": self._build_messages(prompt, system),
            "stream": False,
            "think": think,
            "options": {"temperature": temperature},
        }
        if json_mode:
            payload["format"] = "json"

        data = self._request_with_retry("/api/chat", payload)
        content = data.get("message", {}).get("content", "")
        return strip_thinking_tags(content)

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
        """Stream response chunks from Ollama using /api/chat."""
        payload: dict = {
            "model": self.model,
            "messages": self._build_messages(prompt, system),
            "stream": True,
            "think": think,
            "options": {"temperature": temperature},
        }

        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        msg = chunk.get("message", {})
                        token = msg.get("content", "")
                        if token:
                            yield token
                        if chunk.get("done", False):
                            return
        except URLError as e:
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                f"Is Ollama running? Start it with: ollama serve\n"
                f"Error: {e}"
            ) from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"Ollama request timed out after {self.timeout}s") from e

    def health_check(self) -> bool:
        """Check if Ollama is running by hitting GET /api/tags."""
        try:
            req = Request(f"{self.base_url}/api/tags", method="GET")
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _request_with_retry(self, endpoint: str, payload: dict) -> dict:
        """Make a POST request with exponential backoff retry."""
        body = json.dumps(payload).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            req = Request(
                f"{self.base_url}{endpoint}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except URLError as e:
                last_error = e
                if attempt == 0:
                    raise LLMConnectionError(
                        f"Cannot connect to Ollama at {self.base_url}. "
                        f"Is Ollama running? Start it with: ollama serve\n"
                        f"Error: {e}"
                    ) from e
            except TimeoutError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt
                    time.sleep(wait)

        raise LLMTimeoutError(f"Ollama request failed after {self.max_retries} attempts. Last error: {last_error}")
