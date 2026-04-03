"""LLM backends for featcat."""

from .base import BaseLLM, LLMConnectionError, LLMTimeoutError
from .ollama import OllamaLLM
from .llamacpp import LlamaCppLLM


def create_llm(backend: str = "ollama", **kwargs) -> BaseLLM:
    """Factory to create the appropriate LLM backend."""
    if backend == "ollama":
        return OllamaLLM(**kwargs)
    elif backend == "llamacpp":
        return LlamaCppLLM(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")
