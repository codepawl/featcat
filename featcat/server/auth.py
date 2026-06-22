"""Internal auth helpers for trusted proxy / bearer-token deployments."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from fastapi import Request

    from ..config import Settings

AuthRole = Literal["viewer", "editor", "admin"]


class AuthPrincipal(BaseModel):
    email: str
    role: AuthRole
    groups: list[str]
    auth_type: str


def _split_values(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]


def _header_values(request: Request, names: list[str]) -> list[str]:
    values: list[str] = []
    for name in names:
        raw = request.headers.get(name)
        if not raw:
            continue
        values.extend(_split_values(raw))
    return values


def _normalize(value: str) -> str:
    return value.strip().lower()


def resolve_principal(request: Request, settings: Settings) -> AuthPrincipal | None:
    """Resolve a trusted principal from the bearer token or SSO headers."""
    auth_header = request.headers.get("Authorization", "")
    if settings.server_auth_token and auth_header == f"Bearer {settings.server_auth_token}":
        return AuthPrincipal(email="service@featcat", role="admin", groups=[], auth_type="service")

    identity = ""
    for name in settings.auth_identity_headers:
        identity = request.headers.get(name, "").strip()
        if identity:
            break
    if not identity:
        return None

    groups = _header_values(request, settings.auth_group_headers)
    identity_norm = _normalize(identity)
    groups_norm = {_normalize(group) for group in groups}

    admin_users = {_normalize(user) for user in settings.auth_admin_users}
    editor_users = {_normalize(user) for user in settings.auth_editor_users}
    admin_groups = {_normalize(group) for group in settings.auth_admin_groups}
    editor_groups = {_normalize(group) for group in settings.auth_editor_groups}

    if identity_norm in admin_users or groups_norm & admin_groups:
        role: AuthRole = "admin"
    elif identity_norm in editor_users or groups_norm & editor_groups:
        role = "editor"
    else:
        role = "viewer"

    return AuthPrincipal(email=identity, role=role, groups=groups, auth_type="proxy")


def required_role_for_request(method: str, path: str) -> AuthRole | None:
    """Return the minimum role required for this request, or None if viewer is enough."""
    method = method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return None
    if path.startswith("/api/admin"):
        return "admin"
    if path == "/api/auth/me":
        return None
    if path.startswith("/api/ai/"):
        return None
    if path == "/api/export" or path.startswith("/api/export/"):
        return None
    if path == "/api/online/read":
        return None
    if path.startswith("/api/notifications/"):
        return None
    if method == "DELETE":
        return "admin"
    if method in {"POST", "PUT", "PATCH"}:
        return "editor"
    return None


def can_access(principal: AuthPrincipal, method: str, path: str) -> bool:
    """Check whether a principal can access a request."""
    required = required_role_for_request(method, path)
    if required is None:
        return True
    order = {"viewer": 0, "editor": 1, "admin": 2}
    return order[principal.role] >= order[required]
