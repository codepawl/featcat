"""Integration test for the /api/ai/chat SSE timeout (Fix 1 / Gap 3)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
def db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "chat_timeout.db"))
    db.init_db()
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db, get_llm

    class _StubLLM:
        def health_check(self) -> bool:
            return True

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: _StubLLM()
    return TestClient(app)


async def _slow_chat(self: Any, query: str, history: Any = None) -> AsyncIterator[dict[str, Any]]:
    # Slower than the patched CHAT_TIMEOUT so the deadline always wins.
    await asyncio.sleep(10)
    yield {"type": "token", "content": "never reached"}


def _parse_sse_events(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:") :].strip()
                if payload:
                    events.append(json.loads(payload))
    return events


def test_chat_endpoint_emits_timeout_error_event(monkeypatch: pytest.MonkeyPatch, db: LocalBackend) -> None:
    from featcat.ai import agent as agent_module
    from featcat.server.routes import ai as ai_routes

    # Tight deadline + slow generator → must trip the timeout path.
    monkeypatch.setattr(ai_routes, "CHAT_TIMEOUT", 1)
    monkeypatch.setattr(agent_module.CatalogAgent, "chat", _slow_chat)

    client = _client(db)
    start = time.monotonic()
    resp = client.post("/api/ai/chat", json={"query": "hello"})
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    # Deadline 1s + small buffer for slow CI.
    assert elapsed < 4.0, f"chat handler hung past timeout: {elapsed:.2f}s"

    events = _parse_sse_events(resp.text)
    error_events = [e for e in events if e.get("type") == "error"]
    assert error_events, f"no error event emitted; got events: {events}"
    assert "quá lâu" in error_events[0]["content"], error_events[0]


def test_chat_endpoint_skips_assistant_history_on_timeout(monkeypatch: pytest.MonkeyPatch, db: LocalBackend) -> None:
    """A timed-out turn must not poison session history with a half answer."""
    from featcat.ai import agent as agent_module
    from featcat.server.routes import ai as ai_routes

    monkeypatch.setattr(ai_routes, "CHAT_TIMEOUT", 1)
    monkeypatch.setattr(agent_module.CatalogAgent, "chat", _slow_chat)

    client = _client(db)
    resp = client.post("/api/ai/chat", json={"query": "hello", "session_id": "fixed-id"})
    assert resp.status_code == 200

    # Reach into the lazily-created session manager and inspect the turn.
    from featcat.server.routes.ai import agent_chat

    session_mgr = agent_chat._session_mgr  # type: ignore[attr-defined]
    session = session_mgr.get_or_create("fixed-id")
    roles = [m["role"] for m in session.messages]
    # User turn is always logged. Assistant turn must NOT be logged on timeout.
    assert "user" in roles
    assert "assistant" not in roles, f"assistant turn unexpectedly persisted: {session.messages}"
