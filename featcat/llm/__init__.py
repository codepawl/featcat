"""LLM backends for featcat."""

from .base import BaseLLM as BaseLLM
from .base import LLMConnectionError as LLMConnectionError
from .base import LLMTimeoutError as LLMTimeoutError
from .base import strip_thinking_tags as strip_thinking_tags
from .cached import CachedLLM as CachedLLM
from .llamacpp import LlamaCppLLM as LlamaCppLLM


def create_llm(backend: str = "llamacpp", **kwargs) -> BaseLLM:
    """Create an LLM instance. Only 'llamacpp' backend is supported."""
    if backend in ("llamacpp", "ollama"):
        return LlamaCppLLM(**kwargs)
    msg = f"Unknown LLM backend: {backend}"
    raise ValueError(msg)
