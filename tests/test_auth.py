"""Auth integration tests for internal SSO / bearer-token deployments."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from featcat.catalog.local import LocalBackend
from featcat.config import load_settings
from featcat.server.auth import can_access, resolve_principal
from featcat.server.routes.auth import AccessRequestCreate, list_access_requests, me, request_access

if TYPE_CHECKING:
    from pathlib import Path

pytest.importorskip("fastapi")


def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, token: str | None = None):
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("FEATCAT_LLM_BACKEND", "disabled")
    monkeypatch.setenv("FEATCAT_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("FEATCAT_AUTH_REQUIRED", "true")
    monkeypatch.setenv("FEATCAT_AUTH_ADMIN_GROUPS", '["featcat-admins"]')
    monkeypatch.setenv("FEATCAT_AUTH_EDITOR_GROUPS", '["featcat-editors"]')
    if token is not None:
        monkeypatch.setenv("FEATCAT_SERVER_AUTH_TOKEN", token)
    return load_settings()


def _request(headers: dict[str, str] | None = None):
    return SimpleNamespace(
        headers=headers or {},
        state=SimpleNamespace(principal=None),
        app=SimpleNamespace(state=SimpleNamespace(backend=None)),
    )


def test_auth_me_reports_unauthenticated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    payload = me(_request(), settings)
    assert payload.authenticated is False
    assert payload.required is True
    assert payload.user is None


def test_viewer_can_read_but_cannot_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    principal = resolve_principal(_request({"X-Auth-Request-Email": "viewer@example.com"}), settings)
    assert principal is not None
    assert principal.role == "viewer"
    assert can_access(principal, "GET", "/api/features") is True
    assert can_access(principal, "POST", "/api/sources") is False


def test_editor_can_create_but_not_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    principal = resolve_principal(
        _request(
            {
                "X-Auth-Request-Email": "editor@example.com",
                "X-Auth-Request-Groups": "featcat-editors",
            }
        ),
        settings,
    )
    assert principal is not None
    assert principal.role == "editor"
    assert can_access(principal, "POST", "/api/sources") is True
    assert can_access(principal, "DELETE", "/api/sources/editor-src") is False


def test_admin_can_delete_and_service_token_bypasses_roles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch, token="service-token")
    admin_principal = resolve_principal(
        _request(
            {
                "X-Auth-Request-Email": "admin@example.com",
                "X-Auth-Request-Groups": "featcat-admins",
            }
        ),
        settings,
    )
    assert admin_principal is not None
    assert admin_principal.role == "admin"
    assert can_access(admin_principal, "DELETE", "/api/sources/admin-src") is True

    service_principal = resolve_principal(_request({"Authorization": "Bearer service-token"}), settings)
    assert service_principal is not None
    assert service_principal.role == "admin"
    assert service_principal.auth_type == "service"


def test_access_request_requires_fpt_domain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    backend = LocalBackend(str(tmp_path / "auth.db"))
    backend.init_db()
    request = _request()
    request.app.state.backend = backend

    with pytest.raises(HTTPException):
        request_access(AccessRequestCreate(email="alice@other.com"), request, settings)


def test_access_request_is_persisted_and_listed_for_admin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    backend = LocalBackend(str(tmp_path / "auth.db"))
    backend.init_db()
    request = _request({"X-Auth-Request-Email": "admin@example.com", "X-Auth-Request-Groups": "featcat-admins"})
    request.app.state.backend = backend

    created = request_access(
        AccessRequestCreate(
            email="alice@fpt.com",
            display_name="Alice",
            message="Need access for the data team",
        ),
        request,
        settings,
    )
    assert created.email == "alice@fpt.com"
    assert created.status == "pending"

    listed = list_access_requests(request, settings)
    assert len(listed) == 1
    assert listed[0].email == "alice@fpt.com"
