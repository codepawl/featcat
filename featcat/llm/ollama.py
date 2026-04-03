"""Ollama LLM backend (HTTP API at localhost:11434)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import BaseLLM, LLMConnectionError, LLMTimeoutError

if TYPE_CHECKING:
    from collections.abc import Iterator


class OllamaLLM(BaseLLM):
    """LLM backend using Ollama's HTTP API."""

    def __init__(
        self,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        """Generate a complete response from Ollama."""
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        data = self._request_with_retry("/api/generate", payload)
        return data.get("response", "")

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Stream response chunks from Ollama."""
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    if line:
                        chunk = json.loads(line.decode("utf-8"))
                        token = chunk.get("response", "")
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
