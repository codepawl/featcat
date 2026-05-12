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

    def test_list_features_no_filters(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("list_features", {})
        assert "user_data.age" in result
        assert "user_data.revenue" in result
        assert "Showing 3 of 3" in result

    def test_list_features_filter_by_source(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("list_features", {"source": "user_data", "dtype": "float64"})
        assert "user_data.revenue" in result
        assert "user_data.age" not in result

    def test_list_features_undocumented(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        # All features in fixture have no doc → has_doc=False returns all 3
        result = executor.execute("list_features", {"has_doc": False})
        assert "[no doc]" in result
        assert "user_data.age" in result

    def test_list_features_documented_empty(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("list_features", {"has_doc": True})
        assert "No features match" in result

    def test_count_features_total(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("count_features", {})
        assert "3 features" in result

    def test_count_features_filtered(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("count_features", {"dtype": "bool"})
        assert "1 features" in result
        assert "bool" in result

    def test_catalog_summary(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("catalog_summary", {})
        assert "3 features" in result
        assert "1 sources" in result
        assert "Doc coverage" in result

    def test_features_by_source(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("features_by_source", {})
        assert "user_data: 3 features" in result

    def test_list_groups_empty(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("list_groups", {})
        assert "No feature groups" in result

    def test_get_group_not_found(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("get_group", {"name": "nonexistent"})
        assert "not found" in result

    def test_find_similar_unknown_feature(self, db_with_features: CatalogDB):
        executor = ToolExecutor(db_with_features)
        result = executor.execute("find_similar_features", {"feature_name": "nope.nope"})
        assert "not found" in result

    def test_find_duplicate_pairs_empty(self, db_with_features: CatalogDB):
        """Fixture has 3 unrelated features → no duplicates expected."""
        executor = ToolExecutor(db_with_features)
        result = executor.execute("find_duplicate_pairs", {})
        assert "No duplicate pairs found" in result

    def test_find_duplicate_pairs_with_source(self, db_with_features: CatalogDB):
        """Scope marker should appear when source is passed."""
        executor = ToolExecutor(db_with_features)
        result = executor.execute("find_duplicate_pairs", {"source": "user_data", "threshold": 0.9})
        assert "user_data" in result
        assert "0.90" in result

    def test_find_duplicate_pairs_formats_pairs(self, db_with_features: CatalogDB, monkeypatch):
        """Patched backend returns one pair — verify header + row formatting."""
        executor = ToolExecutor(db_with_features)
        fake_pair = {
            "a": {"name": "user_data.age"},
            "b": {"name": "user_data.revenue"},
            "score": 0.85,
            "reasons": [{"code": "name_similarity", "detail": "x"}, {"code": "schema_match", "detail": "y"}],
        }
        monkeypatch.setattr(
            db_with_features,
            "find_duplicate_pairs",
            lambda threshold, limit, sources=None: ([fake_pair], 1, None),
        )
        result = executor.execute("find_duplicate_pairs", {"threshold": 0.8})
        assert "Found 1 duplicate pair" in result
        assert "user_data.age" in result
        assert "user_data.revenue" in result
        assert "0.850" in result
        assert "name_similarity" in result and "schema_match" in result

    def test_find_duplicate_pairs_clamps_threshold(self, db_with_features: CatalogDB, monkeypatch):
        """threshold below 0.4 / above 0.95 must be clamped."""
        executor = ToolExecutor(db_with_features)
        captured = {}

        def fake(threshold, limit, sources=None):
            captured["t"] = threshold
            captured["l"] = limit
            return ([], 0, None)

        monkeypatch.setattr(db_with_features, "find_duplicate_pairs", fake)
        executor.execute("find_duplicate_pairs", {"threshold": 0.01, "limit": 1000})
        assert captured["t"] == 0.4
        assert captured["l"] == 50  # MAX 50
        executor.execute("find_duplicate_pairs", {"threshold": 0.99})
        assert captured["t"] == 0.95


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

    def test_self_explanatory_tool_skips_second_llm_call(self, db_with_features: CatalogDB):
        """When the tool result is already user-readable, agent streams it directly."""
        from featcat.ai.agent import CatalogAgent

        mock_llm = MagicMock()
        mock_llm.chat.return_value = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_0",
                    "function": {"name": "catalog_summary", "arguments": "{}"},
                }
            ],
            "finish_reason": "tool_calls",
        }
        agent = CatalogAgent(mock_llm, db_with_features)
        events = asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("Tổng quan catalog")))

        # Exactly one LLM round — second prose pass was skipped.
        assert mock_llm.chat.call_count == 1

        tokens = "".join(e["content"] for e in events if e["type"] == "token")
        # VI intro + tool output should appear inline.
        from featcat.ai.agent import _VI_RESULT_INTROS

        assert "Catalog:" in tokens  # from _tool_catalog_summary output
        assert any(intro in tokens for intro in _VI_RESULT_INTROS)
        assert events[-1]["type"] == "done"

    def test_non_self_explanatory_tool_still_calls_llm_twice(self, db_with_features: CatalogDB):
        """search_features needs prose framing — second LLM call must happen."""
        from featcat.ai.agent import CatalogAgent

        mock_llm = MagicMock()
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
            {
                "content": "Found one matching feature.",
                "tool_calls": None,
                "finish_reason": "stop",
            },
        ]
        agent = CatalogAgent(mock_llm, db_with_features)
        asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("find revenue")))
        assert mock_llm.chat.call_count == 2

    def test_list_features_large_result_keeps_second_llm_call(self, db_with_features: CatalogDB):
        """list_features returning > 20 rows isn't self-explanatory; agent still summarises."""
        from featcat.ai.agent import _list_features_short

        # Fixture has 3 features, but the short-threshold check uses the result string.
        short_result = "Showing 5 of 5 matching features:\n- a\n- b\n- c\n- d\n- e"
        long_result = "Showing 30 of 30 matching features:\n" + "\n".join(f"- f{i}" for i in range(30))
        assert _list_features_short(short_result) is True
        assert _list_features_short(long_result) is False
        # Non-matching first line → not detectable, default False.
        assert _list_features_short("No features match those filters.") is False

    def test_intent_classifier_filters_tools_into_llm_call(self, db_with_features: CatalogDB, monkeypatch):
        """Agent must hand the LLM only the intent-matched tool subset, not all 14."""
        # Force the intent filter on regardless of env state.
        import featcat.ai.agent as agent_mod

        monkeypatch.setattr(agent_mod, "_INTENT_FILTER_ON", True)

        mock_llm = MagicMock()
        # No tool calls → exits cleanly after first LLM call.
        mock_llm.chat.return_value = {
            "content": "ok",
            "tool_calls": None,
            "finish_reason": "stop",
        }
        agent = agent_mod.CatalogAgent(mock_llm, db_with_features)
        # "Tóm tắt tình trạng catalog" → summary intent → only catalog_summary.
        asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("Tóm tắt tình trạng catalog")))

        call_args = mock_llm.chat.call_args
        tools_passed = call_args.kwargs["tools"]
        names = [t["function"]["name"] for t in tools_passed]
        assert names == ["catalog_summary"], f"expected catalog_summary only, got {names}"

    def test_intent_filter_off_passes_full_inventory(self, db_with_features: CatalogDB, monkeypatch):
        """FEATCAT_INTENT_FILTER=off bypasses the filter and sends all 14 tools."""
        import featcat.ai.agent as agent_mod
        from featcat.ai.tools import CATALOG_TOOLS

        monkeypatch.setattr(agent_mod, "_INTENT_FILTER_ON", False)

        mock_llm = MagicMock()
        mock_llm.chat.return_value = {"content": "ok", "tool_calls": None, "finish_reason": "stop"}
        agent = agent_mod.CatalogAgent(mock_llm, db_with_features)
        asyncio.get_event_loop().run_until_complete(_collect_events(agent.chat("Tóm tắt catalog")))

        tools_passed = mock_llm.chat.call_args.kwargs["tools"]
        assert tools_passed is CATALOG_TOOLS, "filter-off must pass the original CATALOG_TOOLS object"


# --- Helpers ---


async def _collect_events(gen) -> list[dict]:
    events = []
    async for event in gen:
        events.append(event)
    return events
