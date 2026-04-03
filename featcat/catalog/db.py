"""Backward-compatible alias for LocalBackend.

All new code should use `from featcat.catalog.factory import get_backend` instead.
This module exists so existing tests and imports continue to work.
"""

from __future__ import annotations

from .local import DEFAULT_DB, LocalBackend, _row_to_feature

# CatalogDB is an alias for LocalBackend
CatalogDB = LocalBackend

__all__ = ["CatalogDB", "DEFAULT_DB", "_row_to_feature"]
