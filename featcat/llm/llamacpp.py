"""llama.cpp server LLM backend (HTTP API, typically localhost:8080)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import Request, urlopen

from .base import BaseLLM, LLMConnectionError, LLMTimeoutError, strip_thinking_tags

if TYPE_CHECKING:
    from collections.abc import Iterator


class LlamaCppLLM(BaseLLM):
    """LLM backend using llama.cpp's HTTP server API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: int = 120,
        max_retries: int = 3,
        **kwargs,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
        think: bool = False,
    ) -> str:
        """Generate a complete response from llama.cpp server."""
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload: dict = {
            "prompt": full_prompt,
            "stream": False,
            "temperature": temperature,
            "n_predict": 2048,
        }
        if json_mode:
            payload["json_schema"] = {"type": "object"}
        data = self._request_with_retry("/completion", payload)
        return strip_thinking_tags(data.get("content", ""))

    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        think: bool = False,
    ) -> Iterator[str]:
        """Stream response chunks from llama.cpp server."""
        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        payload = {
            "prompt": full_prompt,
            "stream": True,
            "temperature": temperature,
            "n_predict": 2048,
        }
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}/completion",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if decoded.startswith("data: "):
                        chunk_str = decoded[6:]
                        if chunk_str == "[DONE]":
                            return
                        chunk = json.loads(chunk_str)
                        token = chunk.get("content", "")
                        if token:
                            yield token
        except URLError as e:
            raise LLMConnectionError(
                f"Cannot connect to llama.cpp server at {self.base_url}. "
                f"Is the server running? Start it with: ./server -m model.gguf\n"
                f"Error: {e}"
            ) from e
        except TimeoutError as e:
            raise LLMTimeoutError(f"llama.cpp request timed out after {self.timeout}s") from e

    def health_check(self) -> bool:
        """Check if llama.cpp server is running."""
        try:
            req = Request(f"{self.base_url}/health", method="GET")
            with urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _request_with_retry(self, endpoint: str, payload: dict) -> dict:
        """POST with exponential backoff retry."""
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
                        f"Cannot connect to llama.cpp server at {self.base_url}. Error: {e}"
                    ) from e
            except TimeoutError as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

        raise LLMTimeoutError(f"llama.cpp request failed after {self.max_retries} attempts. Last error: {last_error}")
