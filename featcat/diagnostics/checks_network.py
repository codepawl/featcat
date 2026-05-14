"""Network checks for ``featcat doctor network``.

Probes are bounded to ~1s each. The DB and LLM TCP probes target the same
hostnames the app would use at runtime, derived from ``settings.llamacpp_url``
and ``featcat.db.connection.resolve_url``. Proxy and S3 checks only run when
those env vars are set — otherwise ``SKIP``.
"""

from __future__ import annotations

import os
import socket
import time
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from featcat.db.connection import resolve_backend, resolve_url

from .models import CheckResult, CheckStatus
from .runner import register

if TYPE_CHECKING:
    from featcat.config import Settings


_TCP_TIMEOUT_S = 1.0
_TCP_WARN_MS = 500


def _tcp_probe(host: str, port: int) -> tuple[bool, int, str]:
    """Return (reachable, latency_ms, detail)."""
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=_TCP_TIMEOUT_S):
            pass
    except OSError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        return False, elapsed_ms, str(exc)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return True, elapsed_ms, ""


def _host_port(url: str, *, default_port: int) -> tuple[str | None, int]:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port if parsed.port is not None else default_port
    return host, port


@register("network")
def network_db_tcp(_settings: Settings) -> CheckResult:
    """TCP-connect to the configured DB host. SKIP for SQLite (it's a file)."""
    backend = resolve_backend()
    if backend != "postgres":
        return CheckResult(
            name="network_db_tcp",
            status=CheckStatus.SKIP,
            detail="sqlite — no network endpoint",
        )
    url = resolve_url(backend)
    host, port = _host_port(url, default_port=5432)
    if not host:
        return CheckResult(
            name="network_db_tcp",
            status=CheckStatus.FAIL,
            detail=f"could not parse host from {url}",
        )
    reachable, latency_ms, err = _tcp_probe(host, port)
    if not reachable:
        return CheckResult(
            name="network_db_tcp",
            status=CheckStatus.FAIL,
            detail=f"{host}:{port} unreachable: {err}",
            resolution="Check the postgres service is up and the hostname is resolvable",
            duration_ms=latency_ms,
        )
    status = CheckStatus.WARN if latency_ms > _TCP_WARN_MS else CheckStatus.PASS
    return CheckResult(
        name="network_db_tcp",
        status=status,
        detail=f"{host}:{port} ({latency_ms}ms)",
        duration_ms=latency_ms,
        metadata={"host": host, "port": port, "latency_ms": latency_ms},
    )


@register("network")
def network_llm_tcp(settings: Settings) -> CheckResult:
    """TCP-connect to the llama.cpp hostname."""
    host, port = _host_port(settings.llamacpp_url, default_port=8080)
    if not host:
        return CheckResult(
            name="network_llm_tcp",
            status=CheckStatus.FAIL,
            detail=f"could not parse host from {settings.llamacpp_url}",
        )
    reachable, latency_ms, err = _tcp_probe(host, port)
    if not reachable:
        return CheckResult(
            name="network_llm_tcp",
            status=CheckStatus.FAIL,
            detail=f"{host}:{port} unreachable: {err}",
            resolution="Check the llama.cpp service is up and the hostname is resolvable",
            duration_ms=latency_ms,
        )
    status = CheckStatus.WARN if latency_ms > _TCP_WARN_MS else CheckStatus.PASS
    return CheckResult(
        name="network_llm_tcp",
        status=status,
        detail=f"{host}:{port} ({latency_ms}ms)",
        duration_ms=latency_ms,
        metadata={"host": host, "port": port, "latency_ms": latency_ms},
    )


@register("network")
def network_proxy(settings: Settings) -> CheckResult:
    """When HTTP_PROXY is set, confirm internal hosts are in NO_PROXY."""
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if not proxy:
        return CheckResult(
            name="network_proxy",
            status=CheckStatus.SKIP,
            detail="no proxy configured",
        )
    no_proxy = os.environ.get("NO_PROXY", "")
    internal_hosts: list[str] = []
    llm_host, _ = _host_port(settings.llamacpp_url, default_port=8080)
    if llm_host:
        internal_hosts.append(llm_host)
    backend = resolve_backend()
    if backend == "postgres":
        db_host, _ = _host_port(resolve_url(backend), default_port=5432)
        if db_host:
            internal_hosts.append(db_host)
    if not internal_hosts:
        return CheckResult(
            name="network_proxy",
            status=CheckStatus.SKIP,
            detail="no internal hosts to check",
        )
    no_proxy_tokens = {t.strip() for t in no_proxy.split(",") if t.strip()}
    missing = [h for h in internal_hosts if h not in no_proxy_tokens]
    if not missing:
        return CheckResult(
            name="network_proxy",
            status=CheckStatus.PASS,
            detail=f"NO_PROXY covers {len(internal_hosts)} internal host(s)",
        )
    return CheckResult(
        name="network_proxy",
        status=CheckStatus.WARN,
        detail=f"internal host(s) not in NO_PROXY: {', '.join(missing)}",
        resolution=f"Add to NO_PROXY: {','.join(missing)}",
        metadata={"missing": missing, "no_proxy": no_proxy},
    )


@register("network")
def network_s3(settings: Settings) -> CheckResult:
    """TCP-probe the configured S3 endpoint. SKIP when S3 isn't configured."""
    endpoint = settings.s3_endpoint_url
    if not endpoint:
        return CheckResult(
            name="network_s3",
            status=CheckStatus.SKIP,
            detail="S3 not configured",
        )
    parsed = urlparse(endpoint)
    host = parsed.hostname
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    if not host:
        return CheckResult(
            name="network_s3",
            status=CheckStatus.FAIL,
            detail=f"could not parse host from {endpoint}",
        )
    reachable, latency_ms, err = _tcp_probe(host, port)
    if not reachable:
        return CheckResult(
            name="network_s3",
            status=CheckStatus.WARN,
            detail=f"{host}:{port} unreachable: {err}",
            resolution="Check S3 endpoint URL and credentials; may be expected from this network",
            duration_ms=latency_ms,
        )
    return CheckResult(
        name="network_s3",
        status=CheckStatus.PASS,
        detail=f"{host}:{port} ({latency_ms}ms)",
        duration_ms=latency_ms,
    )
