"""LLM checks for ``featcat doctor llm``.

Probes are HTTP-only — no actual generation. A warm-generation latency check
would routinely exceed the 2s per-check budget; that's a separate operational
concern best left to ``featcat ask`` smokes or pgvector benches.

``/health`` is universal (every llama.cpp build has it). ``/props`` and
``/slots`` are best-effort — when they're disabled or return 404 we emit
``SKIP`` rather than ``FAIL``.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from .models import CheckResult, CheckStatus
from .runner import register

if TYPE_CHECKING:
    from featcat.config import Settings


_HEALTH_WARN_MS = 2000
_HEALTH_TIMEOUT_S = 1.5
_CTX_WARN_TOKENS = 2048


def _get_json(url: str, *, timeout: float = _HEALTH_TIMEOUT_S) -> tuple[int, Any]:
    """GET ``url`` with a short timeout; return (status_code, parsed_json_or_None)."""
    resp = httpx.get(url, timeout=timeout)
    payload: Any = None
    if "application/json" in resp.headers.get("content-type", ""):
        try:
            payload = resp.json()
        except ValueError:
            payload = None
    return resp.status_code, payload


@register("llm")
def llm_reachable(settings: Settings) -> CheckResult:
    """``GET /health`` — the universal llama.cpp probe."""
    url = f"{settings.llamacpp_url.rstrip('/')}/health"
    started = time.monotonic()
    try:
        resp = httpx.get(url, timeout=_HEALTH_TIMEOUT_S)
        elapsed_ms = int((time.monotonic() - started) * 1000)
    except httpx.HTTPError as exc:
        return CheckResult(
            name="llm_reachable",
            status=CheckStatus.FAIL,
            detail=f"{settings.llamacpp_url} unreachable: {exc}",
            resolution="Start the llama.cpp container or check FEATCAT_LLAMACPP_URL",
            duration_ms=int((time.monotonic() - started) * 1000),
        )
    if resp.status_code != 200:
        return CheckResult(
            name="llm_reachable",
            status=CheckStatus.FAIL,
            detail=f"{url} returned {resp.status_code}",
            resolution="Inspect llama.cpp server logs",
            duration_ms=elapsed_ms,
        )
    status = CheckStatus.WARN if elapsed_ms > _HEALTH_WARN_MS else CheckStatus.PASS
    return CheckResult(
        name="llm_reachable",
        status=status,
        detail=f"{settings.llamacpp_url} ({elapsed_ms}ms)",
        resolution="LLM health-probe latency high; check server load" if status is CheckStatus.WARN else None,
        duration_ms=elapsed_ms,
        metadata={"url": settings.llamacpp_url, "latency_ms": elapsed_ms},
    )


@register("llm")
def llm_model(settings: Settings) -> CheckResult:
    """``GET /props`` — confirm the loaded model matches ``settings.llm_model``."""
    url = f"{settings.llamacpp_url.rstrip('/')}/props"
    try:
        status_code, payload = _get_json(url)
    except httpx.HTTPError as exc:
        return CheckResult(
            name="llm_model",
            status=CheckStatus.SKIP,
            detail=f"/props unreachable: {exc}",
        )
    if status_code == 404:
        return CheckResult(
            name="llm_model",
            status=CheckStatus.SKIP,
            detail="/props endpoint not available on this build",
        )
    if status_code != 200 or not isinstance(payload, dict):
        return CheckResult(
            name="llm_model",
            status=CheckStatus.SKIP,
            detail=f"/props returned {status_code}",
        )
    # /props shape varies between llama.cpp versions; check common locations.
    loaded = _extract_loaded_model(payload)
    if loaded is None:
        return CheckResult(
            name="llm_model",
            status=CheckStatus.SKIP,
            detail="/props payload lacks model identifier",
        )
    expected = settings.llm_model
    if expected and expected not in loaded:
        return CheckResult(
            name="llm_model",
            status=CheckStatus.WARN,
            detail=f"loaded={loaded}, expected~={expected}",
            resolution="Check FEATCAT_LLM_MODEL matches the model file llama.cpp loaded",
            metadata={"loaded": loaded, "expected": expected},
        )
    return CheckResult(
        name="llm_model",
        status=CheckStatus.PASS,
        detail=loaded,
        metadata={"loaded": loaded},
    )


@register("llm")
def llm_context(settings: Settings) -> CheckResult:
    """``GET /props`` — confirm ``n_ctx`` is large enough for typical prompts."""
    url = f"{settings.llamacpp_url.rstrip('/')}/props"
    try:
        status_code, payload = _get_json(url)
    except httpx.HTTPError as exc:
        return CheckResult(
            name="llm_context",
            status=CheckStatus.SKIP,
            detail=f"/props unreachable: {exc}",
        )
    if status_code != 200 or not isinstance(payload, dict):
        return CheckResult(
            name="llm_context",
            status=CheckStatus.SKIP,
            detail=f"/props returned {status_code}",
        )
    n_ctx = _extract_n_ctx(payload)
    if n_ctx is None:
        return CheckResult(
            name="llm_context",
            status=CheckStatus.SKIP,
            detail="/props payload lacks n_ctx",
        )
    status = CheckStatus.PASS if n_ctx >= _CTX_WARN_TOKENS else CheckStatus.WARN
    return CheckResult(
        name="llm_context",
        status=status,
        detail=f"n_ctx={n_ctx}",
        resolution=f"Raise --ctx-size to >={_CTX_WARN_TOKENS} on the llama.cpp command"
        if status is CheckStatus.WARN
        else None,
        metadata={"n_ctx": n_ctx},
    )


@register("llm")
def llm_slots(settings: Settings) -> CheckResult:
    """``GET /slots`` — count free vs. busy slots. SKIP on builds without the endpoint."""
    url = f"{settings.llamacpp_url.rstrip('/')}/slots"
    try:
        status_code, payload = _get_json(url)
    except httpx.HTTPError as exc:
        return CheckResult(
            name="llm_slots",
            status=CheckStatus.SKIP,
            detail=f"/slots unreachable: {exc}",
        )
    if status_code == 404 or status_code == 501:
        return CheckResult(
            name="llm_slots",
            status=CheckStatus.SKIP,
            detail="/slots endpoint not available on this build",
        )
    if status_code != 200 or not isinstance(payload, list):
        return CheckResult(
            name="llm_slots",
            status=CheckStatus.SKIP,
            detail=f"/slots returned {status_code}",
        )
    total = len(payload)
    if total == 0:
        return CheckResult(
            name="llm_slots",
            status=CheckStatus.SKIP,
            detail="/slots returned empty list",
        )
    busy = sum(1 for s in payload if isinstance(s, dict) and s.get("is_processing"))
    free = total - busy
    if free == 0:
        status = CheckStatus.WARN
        detail = f"all {total} slot(s) busy"
        resolution = "Slots saturated — raise --parallel on llama.cpp or queue depth on the API"
    else:
        status = CheckStatus.PASS
        detail = f"{free}/{total} slot(s) free"
        resolution = None
    return CheckResult(
        name="llm_slots",
        status=status,
        detail=detail,
        resolution=resolution,
        metadata={"total": total, "busy": busy, "free": free},
    )


def _extract_loaded_model(props: dict[str, Any]) -> str | None:
    """Pluck the loaded-model name out of the various /props shapes llama.cpp emits."""
    # Newer builds put it at the top level.
    for key in ("model", "model_alias", "model_path"):
        value = props.get(key)
        if isinstance(value, str) and value:
            return value
    # Older builds nest it under default_generation_settings.
    settings = props.get("default_generation_settings")
    if isinstance(settings, dict):
        for key in ("model", "model_path"):
            value = settings.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _extract_n_ctx(props: dict[str, Any]) -> int | None:
    """Pluck n_ctx out of the /props payload."""
    value = props.get("n_ctx")
    if isinstance(value, int):
        return value
    settings = props.get("default_generation_settings")
    if isinstance(settings, dict):
        value = settings.get("n_ctx")
        if isinstance(value, int):
            return value
    return None
