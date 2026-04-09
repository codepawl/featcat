"""LLM backends for featcat."""

from .base import BaseLLM as BaseLLM
from .base import LLMConnectionError as LLMConnectionError
from .base import LLMTimeoutError as LLMTimeoutError
from .llamacpp import LlamaCppLLM as LlamaCppLLM
from .ollama import OllamaLLM as OllamaLLM


def create_llm(backend: str = "llamacpp", **kwargs) -> BaseLLM:
    """Factory to create the appropriate LLM backend."""
    if backend == "ollama":
        return OllamaLLM(**kwargs)
    elif backend == "llamacpp":
        return LlamaCppLLM(**kwargs)
    else:
        raise ValueError(f"Unknown LLM backend: {backend}")
