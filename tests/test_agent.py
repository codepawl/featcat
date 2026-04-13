"""Tests for the AI agent layer."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from featcat.ai.executor import ToolExecutor
from featcat.ai.fallback import FallbackAgent
from featcat.ai.session import ChatSession, SessionManager
from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature


@pytest.fixture()
def db_with_features(tmp_path: Path):
    """Create a DB with features for agent tests."""
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="user_data", path="/data/users.parquet")
    db.add_source(source)
    for col, dtype in [("age", "int64"), ("revenue", "float64"), ("churn", "bool")]:
        f = Feature(
            name=f"user_data.{col}",
            data_source_id=source.id,
            column_name=col,
            dtype=dtype,
            description=f"User {col} feature",
            tags=["user"],
            owner="ds-team",
            stats={"mean": 42.0, "null_ratio": 0.01} if dtype != "bool" else {},
        )
        db.upsert_feature(f)
    yield db
    db.close()


# --- ToolExecutor tests ---


class TestToolExecutor:
    def test_search_features(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("search_features", {"query": "revenue"})
        assert "user_data.revenue" in result

    def test_search_no_results(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("search_features", {"query": "zzz_nonexistent"})
        assert "No features found" in result

    def test_get_feature_detail(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("get_feature_detail", {"feature_name": "user_data.age"})
        assert "user_data.age" in result
        assert "int64" in result
        assert "mean" in result

    def test_get_feature_not_found(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("get_feature_detail", {"feature_name": "nope.nope"})
        assert "not found" in result

    def test_compare_features(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("compare_features", {"feature_names": "user_data.age, user_data.revenue"})
        assert "user_data.age" in result
        assert "user_data.revenue" in result
        assert "Comparison" in result

    def test_compare_needs_two(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("compare_features", {"feature_names": "user_data.age"})
        assert "at least 2" in result

    def test_list_sources(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("list_sources", {})
        assert "user_data" in result

    def test_unknown_tool(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("nonexistent_tool", {})
        assert "unknown tool" in result

    def test_result_truncation(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        # Mock a tool that returns a huge string
        executor._tool_search_features = lambda query: "x" * 5000  # type: ignore[attr-defined]
        result = executor.execute("search_features", {"query": "test"})
        assert len(result) <= 1600  # 1500 + truncation message
        assert "truncated" in result


# --- SessionManager tests ---


class TestSessionManager:
    def test_create_session(self):
        mgr = SessionManager()
        session = mgr.get_or_create("test-1")
        assert session.session_id == "test-1"
        assert session.messages == []

    def test_get_existing_session(self):
        mgr = SessionManager()
        s1 = mgr.get_or_create("test-1")
        s1.add_message("user", "hello")
        s2 = mgr.get_or_create("test-1")
        assert len(s2.messages) == 1
        assert s2.messages[0]["content"] == "hello"

    def test_message_trimming(self):
        session = ChatSession(session_id="trim-test")
        for i in range(25):
            session.add_message("user", f"msg {i}")
        assert len(session.messages) <= ChatSession.MAX_MESSAGES

    def test_history_returns_last_6(self):
        session = ChatSession(session_id="hist-test")
        for i in range(10):
            session.add_message("user", f"msg {i}")
            session.add_message("assistant", f"reply {i}")
        history = session.get_history()
        assert len(history) == 6

    def test_ttl_eviction(self):
        mgr = SessionManager()
        mgr.TTL_SECONDS = 0  # Expire immediately
        mgr.get_or_create("old-session")
        time.sleep(0.01)
        mgr._cleanup_expired()
        # Creating new session should not find old one
        s = mgr.get_or_create("old-session")
        assert s.messages == []

    def test_max_sessions_eviction(self):
        mgr = SessionManager()
        mgr.MAX_SESSIONS = 3
        for i in range(4):
            mgr.get_or_create(f"session-{i}")
        assert len(mgr._sessions) <= 3


# --- FallbackAgent tests ---


class TestFallbackAgent:
    def test_greeting(self, db_with_features: CatalogDB):
        agent = FallbackAgent(db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("hello")))
        tokens = [e["content"] for e in events if e["type"] == "token"]
        assert any("featcat" in t for t in tokens)
        assert events[-1]["type"] == "done"

    def test_search(self, db_with_features: CatalogDB):
        agent = FallbackAgent(db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("revenue")))
        tokens = [e["content"] for e in events if e["type"] == "token"]
        assert any("user_data.revenue" in t for t in tokens)

    def test_no_results(self, db_with_features: CatalogDB):
        agent = FallbackAgent(db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("zzz_nothing")))
        tokens = [e["content"] for e in events if e["type"] == "token"]
        assert any("Không tìm thấy" in t for t in tokens)


# --- CatalogAgent tests ---


class TestCatalogAgent:
    def test_text_response_no_tools(self, db_with_features: CatalogDB):
        """LLM responds with text, no tool calls."""
        from featcat.ai.agent import CatalogAgent

        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "content": "Xin chào! Mình là featcat.",
            "tool_calls": None,
            "finish_reason": "stop",
        }
        agent = CatalogAgent(mock_llm, db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("hello")))
        tokens = "".join(e["content"] for e in events if e["type"] == "token")
        assert "featcat" in tokens
        assert events[-1]["type"] == "done"

    def test_tool_call_then_response(self, db_with_features: CatalogDB):
        """LLM calls a tool, then responds with text."""
        from featcat.ai.agent import CatalogAgent

        mock_llm = MagicMock()
        # First call: tool call
        mock_llm.chat.side_effect = [
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_0",
                        "function": {"name": "search_features", "arguments": '{"query": "revenue"}'},
                    }
                ],
                "finish_reason": "tool_calls",
            },
            # Second call: text response after seeing tool result
            {
                "content": "Found user_data.revenue — a float64 feature tracking user revenue.",
                "tool_calls": None,
                "finish_reason": "stop",
            },
        ]
        agent = CatalogAgent(mock_llm, db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("find revenue features")))

        types = [e["type"] for e in events]
        assert "tool_call" in types
        assert "tool_result" in types
        assert "token" in types
        assert types[-1] == "done"

        # Check tool call details
        tc_event = next(e for e in events if e["type"] == "tool_call")
        assert tc_event["name"] == "search_features"

    def test_llm_error_yields_error(self, db_with_features: CatalogDB):
        """LLM raises exception — agent yields error and stops."""
        from featcat.ai.agent import CatalogAgent

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = ConnectionError("LLM down")
        agent = CatalogAgent(mock_llm, db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("test")))
        tokens = "".join(e.get("content", "") for e in events if e["type"] == "token")
        assert "LLM error" in tokens


# --- Helpers ---


async def _collect_events(gen) -> list[dict]:
    events = []
    async for event in gen:
        events.append(event)
    return events
