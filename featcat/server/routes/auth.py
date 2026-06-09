"""Auth status endpoint for internal SSO / bearer-token deployments."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...catalog.local import LocalBackend
from ...config import Settings
from ...db.models import AccessRequest
from ..auth import AuthPrincipal, resolve_principal
from ..deps import get_settings

router = APIRouter()


DEFAULT_ALLOWED_EMAIL_DOMAINS = ["fpt.com"]


class AuthState(BaseModel):
    authenticated: bool
    required: bool
    user: AuthPrincipal | None = None


class AuthConfig(BaseModel):
    company_name: str = "FPT"
    allowed_email_domains: list[str] = Field(default_factory=lambda: DEFAULT_ALLOWED_EMAIL_DOMAINS.copy())
    request_access_enabled: bool = True


class AccessRequestCreate(BaseModel):
    email: str
    display_name: str | None = None
    message: str | None = None


class AccessRequestItem(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    message: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_domain(email: str) -> str:
    if "@" not in email:
        raise ValueError("Invalid email address")
    return email.rsplit("@", 1)[-1].strip().lower()


def _allowed_domains(settings: Settings) -> list[str]:
    domains = [domain.strip().lower() for domain in settings.auth_allowed_email_domains if domain.strip()]
    return domains or DEFAULT_ALLOWED_EMAIL_DOMAINS


def _require_admin(request: Request, settings: Settings) -> AuthPrincipal:
    principal = getattr(request.state, "principal", None) or resolve_principal(request, settings)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return principal


def _get_backend(request: Request) -> LocalBackend:
    backend = request.app.state.backend
    if not isinstance(backend, LocalBackend):
        raise HTTPException(status_code=500, detail="Access requests require the local catalog backend")
    return backend


@router.get("/me", response_model=AuthState)
def me(request: Request, settings: Settings = Depends(get_settings)):  # noqa: B008
    """Return the current principal if one is present."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        principal = resolve_principal(request, settings)
    return AuthState(
        authenticated=principal is not None,
        required=settings.auth_required or bool(settings.server_auth_token),
        user=principal,
    )


@router.get("/config", response_model=AuthConfig)
def config(settings: Settings = Depends(get_settings)):  # noqa: B008
    """Return company-login configuration for the auth panel."""
    return AuthConfig(allowed_email_domains=_allowed_domains(settings))


@router.post("/request-access", response_model=AccessRequestItem, status_code=status.HTTP_201_CREATED)
def request_access(payload: AccessRequestCreate, request: Request, settings: Settings = Depends(get_settings)):  # noqa: B008
    """Store an access request for later admin review."""
    email = _normalize_email(payload.email)
    try:
        domain = _email_domain(email)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    if domain not in _allowed_domains(settings):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Please use one of: {', '.join('@' + d for d in _allowed_domains(settings))}",
        )

    backend = _get_backend(request)
    now = datetime.now(timezone.utc)
    with backend.session() as session:
        existing = session.execute(select(AccessRequest).where(AccessRequest.email == email)).scalar_one_or_none()
        if existing is None:
            existing = AccessRequest(
                id=f"req-{uuid4().hex}",
                email=email,
                display_name=payload.display_name.strip() if payload.display_name else None,
                message=payload.message.strip() if payload.message else None,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            session.add(existing)
        else:
            existing.display_name = payload.display_name.strip() if payload.display_name else existing.display_name
            existing.message = payload.message.strip() if payload.message else existing.message
            existing.status = "pending"
            existing.updated_at = now
        session.commit()
        session.refresh(existing)

        return AccessRequestItem(
            id=existing.id,
            email=existing.email,
            display_name=existing.display_name,
            message=existing.message,
            status=existing.status,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )


@router.get("/access-requests", response_model=list[AccessRequestItem])
def list_access_requests(request: Request, settings: Settings = Depends(get_settings)):  # noqa: B008
    """List submitted access requests for admin review."""
    _require_admin(request, settings)
    backend = _get_backend(request)
    with backend.session() as session:
        rows = session.execute(select(AccessRequest).order_by(AccessRequest.created_at.desc())).scalars().all()
        return [
            AccessRequestItem(
                id=row.id,
                email=row.email,
                display_name=row.display_name,
                message=row.message,
                status=row.status,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
