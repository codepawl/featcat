"""Unit tests for ``featcat.diagnostics.checks_llm``.

llama.cpp endpoints are mocked via a respx-style ``MockTransport`` shim so
tests don't need a running server. Each test pins the exact HTTP response
shape llama.cpp would return.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from featcat.config import Settings
from featcat.diagnostics import CheckStatus
from featcat.diagnostics.checks_llm import llm_context, llm_model, llm_reachable, llm_slots

if TYPE_CHECKING:
    from collections.abc import Callable


def _mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


@pytest.fixture()
def settings() -> Settings:
    return Settings(llamacpp_url="http://llm.test:8080", llm_model="gemma-4-E2B-it")


def _install(monkeypatch: pytest.MonkeyPatch, routes: dict[str, tuple[int, Any]]) -> None:
    """Install an httpx mock that serves each ``path: (status_code, json_payload)`` mapping."""

    def handler(request: httpx.Request) -> httpx.Response:
        spec = routes.get(request.url.path)
        if spec is None:
            return httpx.Response(404)
        status, payload = spec
        if payload is None:
            return httpx.Response(status)
        return httpx.Response(status, content=json.dumps(payload), headers={"content-type": "application/json"})

    real_client = httpx.Client(transport=_mock_transport(handler))

    def fake_get(url: str, *_args: object, **_kwargs: object) -> httpx.Response:
        return real_client.get(url)

    monkeypatch.setattr("featcat.diagnostics.checks_llm.httpx.get", fake_get)


class TestLlmReachable:
    def test_pass_on_200(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/health": (200, {"status": "ok"})})
        result = llm_reachable(settings)
        assert result.status is CheckStatus.PASS

    def test_fail_on_500(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/health": (500, None)})
        result = llm_reachable(settings)
        assert result.status is CheckStatus.FAIL
        assert "500" in result.detail
        assert result.resolution is not None

    def test_fail_on_network_error(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("nope")

        real_client = httpx.Client(transport=_mock_transport(boom))

        def fake_get(url: str, *_args: object, **_kwargs: object) -> httpx.Response:
            return real_client.get(url)

        monkeypatch.setattr("featcat.diagnostics.checks_llm.httpx.get", fake_get)
        result = llm_reachable(settings)
        assert result.status is CheckStatus.FAIL
        assert "unreachable" in result.detail


class TestLlmModel:
    def test_pass_on_matching_model(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (200, {"model": "models/gemma-4-E2B-it-Q4_K_M.gguf"})})
        result = llm_model(settings)
        assert result.status is CheckStatus.PASS

    def test_warn_on_mismatched_model(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (200, {"model": "models/llama-3-8b.gguf"})})
        result = llm_model(settings)
        assert result.status is CheckStatus.WARN
        assert result.resolution is not None

    def test_skip_on_404(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (404, None)})
        result = llm_model(settings)
        assert result.status is CheckStatus.SKIP

    def test_skip_on_missing_model_key(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (200, {"some_other_key": "x"})})
        result = llm_model(settings)
        assert result.status is CheckStatus.SKIP


class TestLlmContext:
    def test_pass_when_large_enough(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (200, {"n_ctx": 4096})})
        result = llm_context(settings)
        assert result.status is CheckStatus.PASS
        assert result.metadata["n_ctx"] == 4096

    def test_warn_when_small(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (200, {"n_ctx": 1024})})
        result = llm_context(settings)
        assert result.status is CheckStatus.WARN

    def test_skip_when_props_missing(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/props": (404, None)})
        result = llm_context(settings)
        assert result.status is CheckStatus.SKIP


class TestLlmSlots:
    def test_pass_with_free_slots(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(
            monkeypatch,
            {
                "/slots": (
                    200,
                    [{"is_processing": False}, {"is_processing": True}, {"is_processing": False}],
                )
            },
        )
        result = llm_slots(settings)
        assert result.status is CheckStatus.PASS
        assert result.metadata == {"total": 3, "busy": 1, "free": 2}

    def test_warn_when_all_busy(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/slots": (200, [{"is_processing": True}] * 4)})
        result = llm_slots(settings)
        assert result.status is CheckStatus.WARN
        assert result.resolution is not None

    def test_skip_on_404(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
        _install(monkeypatch, {"/slots": (404, None)})
        result = llm_slots(settings)
        assert result.status is CheckStatus.SKIP
