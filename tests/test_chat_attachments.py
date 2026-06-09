"""Integration test for the /api/ai/chat attachments (file uploads)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


@pytest.fixture
def db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "chat_attachments.db"))
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


def test_chat_with_attachments_injects_context(db: LocalBackend, monkeypatch: pytest.MonkeyPatch) -> None:
    from featcat.ai import agent as agent_module

    captured_query = None

    async def mock_agent_chat(
        self: Any,
        user_message: str,
        history: Any = None,
        context_summary: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        nonlocal captured_query
        captured_query = user_message
        yield {"type": "token", "content": "mocked response"}
        yield {"type": "done"}

    monkeypatch.setattr(agent_module.CatalogAgent, "chat", mock_agent_chat)

    client = _client(db)
    payload = {
        "query": "Please analyze this schema.",
        "session_id": "test-attach-session",
        "attachments": [
            {"filename": "schema.sql", "content": "CREATE TABLE users (id INT);"},
            {"filename": "data.csv", "content": "id,name\n1,alice"},
        ],
    }
    resp = client.post("/api/ai/chat", json=payload)
    assert resp.status_code == 200

    # 1. Verify attachments were injected into the LLM query
    assert captured_query is not None
    assert "=== FILE: schema.sql ===" in captured_query
    assert "CREATE TABLE users (id INT);" in captured_query
    assert "=== FILE: data.csv ===" in captured_query
    assert "id,name\n1,alice" in captured_query
    assert "User Question: Please analyze this schema." in captured_query

    # 2. Verify clean history reference is stored instead of full context
    from featcat.server.routes.ai import agent_chat

    session_mgr = agent_chat._session_mgr  # type: ignore[attr-defined]
    session = session_mgr.get_or_create("test-attach-session")

    assert len(session.messages) > 0
    user_msg = session.messages[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "[Attached: schema.sql, data.csv] Please analyze this schema."
