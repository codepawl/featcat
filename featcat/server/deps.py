"""FastAPI dependency injection helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request  # noqa: TC002

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend
    from ..config import Settings


def get_db(request: Request) -> CatalogBackend:
    """Return the shared catalog backend from app state."""
    return request.app.state.backend


def get_settings(request: Request) -> Settings:
    """Return the shared settings from app state."""
    return request.app.state.settings


def get_llm(request: Request):
    """Return the shared LLM instance from app state (may be None)."""
    return request.app.state.llm


def get_scheduler(request: Request):
    """Return the shared scheduler from app state."""
    return request.app.state.scheduler
