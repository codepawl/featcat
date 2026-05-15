"""TUI widgets must accept Textual's standard `id` kwarg."""

from __future__ import annotations

import pytest

textual = pytest.importorskip("textual")  # noqa: F841


def test_stats_bar_accepts_id() -> None:
    from featcat.tui.widgets.stats_bar import StatsBar

    bar = StatsBar(id="stats-bar")
    assert bar.id == "stats-bar"


def test_stats_bar_accepts_classes_and_disabled() -> None:
    from featcat.tui.widgets.stats_bar import StatsBar

    bar = StatsBar(id="x", classes="foo", disabled=True)
    assert bar.id == "x"
    assert "foo" in bar.classes
    assert bar.disabled is True


def test_stats_bar_keeps_stat_init_values() -> None:
    from featcat.tui.widgets.stats_bar import StatsBar

    bar = StatsBar(total_features=5, total_sources=2, doc_coverage=80.0, alerts=1, id="x")
    assert bar.total_features == 5
    assert bar.alerts == 1


def test_feature_table_accepts_id() -> None:
    from featcat.tui.widgets.feature_table import FeatureTable

    table = FeatureTable(id="feature-table")
    assert table.id == "feature-table"


def test_alert_list_accepts_id() -> None:
    from featcat.tui.widgets.alert_list import AlertList

    widget = AlertList(id="alert-list")
    assert widget.id == "alert-list"


def test_chat_messages_accepts_id() -> None:
    from featcat.tui.widgets.chat_messages import ChatMessages

    widget = ChatMessages(id="chat-messages")
    assert widget.id == "chat-messages"


def test_feature_detail_accepts_id() -> None:
    from featcat.tui.widgets.feature_detail import FeatureDetail

    widget = FeatureDetail(id="feature-detail")
    assert widget.id == "feature-detail"
