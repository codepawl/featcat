"""Factory for creating the appropriate catalog backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import CatalogBackend


def get_backend() -> CatalogBackend:
    """Return LocalBackend or RemoteBackend based on config.

    If FEATCAT_SERVER_URL is set, returns RemoteBackend.
    Otherwise returns LocalBackend with the configured db path.
    """
    from ..config import load_settings

    settings = load_settings()

    if settings.server_url:
        from .remote import RemoteBackend

        return RemoteBackend(settings.server_url)
    else:
        from .local import LocalBackend

        return LocalBackend(settings.catalog_db_path)
