"""featcat API server package."""

from __future__ import annotations


def create_app():
    """Create and configure the FastAPI application."""
    from .app import build_app

    return build_app()
