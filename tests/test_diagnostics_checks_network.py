"""Tests for ``featcat.diagnostics.checks_network``.

TCP probes are tested by pointing them at an in-process listening socket
(bind to 127.0.0.1:0 so the OS picks a free port) for the PASS path, and
at an unbound port for the FAIL path.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING

import pytest

from featcat.config import Settings
from featcat.diagnostics import CheckStatus
from featcat.diagnostics.checks_network import network_llm_tcp, network_proxy, network_s3

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def listening_port() -> Generator[int, None, None]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        yield sock.getsockname()[1]
    finally:
        sock.close()


class TestNetworkLlmTcp:
    def test_pass_when_reachable(self, listening_port: int) -> None:
        settings = Settings(llamacpp_url=f"http://127.0.0.1:{listening_port}")
        result = network_llm_tcp(settings)
        assert result.status is CheckStatus.PASS
        assert result.metadata["port"] == listening_port

    def test_fail_when_closed(self) -> None:
        # Port 1 is virtually never listening; quick fail path.
        settings = Settings(llamacpp_url="http://127.0.0.1:1")
        result = network_llm_tcp(settings)
        assert result.status is CheckStatus.FAIL
        assert result.resolution is not None


class TestNetworkProxy:
    def test_skip_when_no_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HTTP_PROXY", raising=False)
        monkeypatch.delenv("HTTPS_PROXY", raising=False)
        result = network_proxy(Settings())
        assert result.status is CheckStatus.SKIP

    def test_pass_when_no_proxy_covers_hosts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://corp-proxy:8080")
        monkeypatch.setenv("NO_PROXY", "llm-host,postgres,localhost")
        monkeypatch.delenv("FEATCAT_DB_BACKEND", raising=False)
        settings = Settings(llamacpp_url="http://llm-host:8080")
        result = network_proxy(settings)
        assert result.status is CheckStatus.PASS

    def test_warn_when_hosts_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HTTP_PROXY", "http://corp-proxy:8080")
        monkeypatch.setenv("NO_PROXY", "localhost")
        monkeypatch.delenv("FEATCAT_DB_BACKEND", raising=False)
        settings = Settings(llamacpp_url="http://llm-host:8080")
        result = network_proxy(settings)
        assert result.status is CheckStatus.WARN
        assert "llm-host" in (result.resolution or "")


class TestNetworkS3:
    def test_skip_when_not_configured(self) -> None:
        result = network_s3(Settings())
        assert result.status is CheckStatus.SKIP

    def test_pass_when_reachable(self, listening_port: int) -> None:
        settings = Settings(s3_endpoint_url=f"http://127.0.0.1:{listening_port}")
        result = network_s3(settings)
        assert result.status is CheckStatus.PASS

    def test_warn_when_unreachable(self) -> None:
        settings = Settings(s3_endpoint_url="http://127.0.0.1:1")
        result = network_s3(settings)
        # S3 unreachable is WARN (may be expected from this network), not FAIL.
        assert result.status is CheckStatus.WARN
