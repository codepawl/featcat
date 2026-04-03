"""Abstract plugin interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..catalog.db import CatalogDB
from ..llm.base import BaseLLM


class PluginResult(BaseModel):
    """Standard result returned by all plugins."""

    status: str = "success"  # "success" | "error" | "partial"
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class BasePlugin(ABC):
    """Abstract base class for featcat plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name (e.g., 'discovery', 'autodoc')."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what this plugin does."""

    @abstractmethod
    def execute(
        self,
        catalog_db: CatalogDB,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        """Execute the plugin logic."""
