"""AI agent layer for featcat — agentic chat with tool calling."""

from __future__ import annotations

from .agent import CatalogAgent
from .fallback import FallbackAgent
from .session import SessionManager

__all__ = ["CatalogAgent", "FallbackAgent", "SessionManager"]
