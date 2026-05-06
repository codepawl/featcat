"""Tests for T1.5a — Celery app + first migrated task.

Skipped entirely when celery isn't installed (operators install via the
``[tasks]`` extra). With celery present, tests run with
``CELERY_TASK_ALWAYS_EAGER=True`` so tasks execute synchronously in-process
and we don't need a live Redis broker.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest

celery = pytest.importorskip("celery")

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def eager_celery():
    """Force Celery into eager mode so tasks run synchronously."""
    from featcat.tasks.app import app

    prior = {
        "task_always_eager": app.conf.task_always_eager,
        "task_eager_propagates": app.conf.task_eager_propagates,
    }
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield app
    app.conf.task_always_eager = prior["task_always_eager"]
    app.conf.task_eager_propagates = prior["task_eager_propagates"]


class TestCeleryApp:
    def test_app_constructed(self) -> None:
        from featcat.tasks.app import app

        assert app.main == "featcat"

    def test_queue_routes_registered(self) -> None:
        from featcat.tasks.app import app

        routes = app.conf.task_routes
        assert routes["featcat.tasks.monitoring.*"]["queue"] == "monitoring"
        assert routes["featcat.tasks.docs.*"]["queue"] == "docs"
        assert routes["featcat.tasks.sources.*"]["queue"] == "sources"

    def test_default_queue_and_priority(self) -> None:
        from featcat.tasks.app import app

        assert app.conf.task_default_queue == "default"
        assert app.conf.task_default_priority == 5

    def test_beat_schedule_includes_monitor_check(self) -> None:
        from featcat.tasks.app import app

        names = list(app.conf.beat_schedule.keys())
        assert "monitor-check-every-6h" in names

    def test_acks_late_and_prefetch(self) -> None:
        """Long-running tasks shouldn't disappear if a worker dies mid-flight,
        and prefetch=1 ensures fair dispatch for slow doc-gen jobs."""
        from featcat.tasks.app import app

        assert app.conf.task_acks_late is True
        assert app.conf.worker_prefetch_multiplier == 1


class TestMonitorCheckTask:
    def test_task_name_matches_route(self) -> None:
        from featcat.tasks.monitoring import monitor_check

        assert monitor_check.name == "featcat.tasks.monitoring.monitor_check"

    def test_runs_eagerly_and_returns_status(self, eager_celery: object, tmp_path: Path) -> None:
        """Apply the task and confirm it routes through MonitoringPlugin
        without crashing on a clean catalog. Heavy-lifting LLM + plugin
        internals are mocked — we're testing the wrapper, not the plugin."""
        from featcat.tasks import monitoring as mon_mod

        canned_result = mock.Mock(status="success", data={"checks": 0})
        plugin_cls = mock.Mock()
        plugin_cls.return_value.execute.return_value = canned_result

        with (
            mock.patch("featcat.plugins.monitoring.MonitoringPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
            mock.patch("featcat.llm.create_llm") as create_llm,
        ):
            backend = mock.Mock()
            get_backend.return_value = backend
            create_llm.return_value = mock.Mock()
            result = mon_mod.monitor_check.apply().get()

        assert result["status"] == "success"
        assert result["data"] == {"checks": 0}
        backend.close.assert_called_once()

    def test_continues_when_llm_unavailable(self, eager_celery: object) -> None:
        """If create_llm raises, the task must still run with llm=None."""
        from featcat.tasks import monitoring as mon_mod

        canned_result = mock.Mock(status="success", data={})
        plugin_cls = mock.Mock()
        plugin_cls.return_value.execute.return_value = canned_result
        with (
            mock.patch("featcat.plugins.monitoring.MonitoringPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
            mock.patch("featcat.llm.create_llm", side_effect=RuntimeError("no llm")),
        ):
            get_backend.return_value = mock.Mock()
            result = mon_mod.monitor_check.apply().get()
        assert result["status"] == "success"
        plugin_cls.return_value.execute.assert_called_once()
        # Second positional arg is `llm` — should be None when create_llm raised.
        call_args = plugin_cls.return_value.execute.call_args
        assert call_args.args[1] is None or call_args.kwargs.get("llm") is None
