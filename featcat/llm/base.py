"""Abstract LLM interface."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


class LLMConnectionError(Exception):
    """Raised when the LLM server is unreachable."""


class LLMTimeoutError(Exception):
    """Raised when the LLM request times out after retries."""


class BaseLLM(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        json_mode: bool = False,
    ) -> str:
        """Generate a text response from the LLM."""

    @abstractmethod
    def stream(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
    ) -> Iterator[str]:
        """Stream response chunks from the LLM."""

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the LLM server is running and reachable."""

    def generate_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.1,
        max_retries: int = 1,
    ) -> dict:
        """Generate a JSON response, with retry on parse failure.

        Uses json_mode when available for more reliable output.
        Attempts to extract JSON from the response text. If parsing fails,
        sends a fix-up prompt asking the LLM to correct the output.
        """
        response = self.generate(prompt, system=system, temperature=temperature, json_mode=True)
        response = strip_thinking_tags(response)

        for attempt in range(max_retries + 1):
            parsed = _extract_json(response)
            if parsed is not None:
                return parsed

            if attempt < max_retries:
                fix_prompt = (
                    f"Your previous response was not valid JSON. "
                    f"Here is what you returned:\n\n{response}\n\n"
                    f"Please return ONLY a valid JSON object, no markdown fences or extra text."
                )
                response = self.generate(fix_prompt, system=system, temperature=0.0)

        raise ValueError(f"Failed to parse JSON after {max_retries + 1} attempts. Last response: {response[:500]}")


def strip_thinking_tags(text: str) -> str:
    """Strip <think>...</think> reasoning blocks from LLM response."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from text that may contain markdown fences."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fences
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } or [ ... ] block
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = text.find(open_char)
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == open_char:
                    depth += 1
                elif text[i] == close_char:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break

    return None
