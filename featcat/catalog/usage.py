"""Usage tracking utilities."""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import CatalogBackend


def resolve_user() -> str:
    """Resolve current user: FEATCAT_USER env > os.getlogin() > 'unknown'."""
    user = os.environ.get("FEATCAT_USER")
    if user:
        return user
    try:
        return os.getlogin()
    except OSError:
        return "unknown"


def log_feature_usage(
    db: CatalogBackend,
    feature_id: str,
    action: str,
    context: str = "",
) -> None:
    """Log a usage event for a feature. Silently ignores errors."""
    with contextlib.suppress(Exception):
        db.log_usage(feature_id, action, user=resolve_user(), context=context)
