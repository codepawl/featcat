"""Tests for T1.5a/b — Celery app + the four migrated jobs.

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

    def test_beat_schedule_includes_all_t1_5b_jobs(self) -> None:
        """T1.5b: doc_generate, source_scan, baseline_refresh must be on
        the beat schedule with the same crons the in-process scheduler
        uses."""
        from featcat.tasks.app import app

        names = set(app.conf.beat_schedule.keys())
        assert {"doc-generate-daily", "source-scan-daily", "baseline-refresh-weekly"} <= names
        assert app.conf.beat_schedule["doc-generate-daily"]["task"] == "featcat.tasks.docs.doc_generate"
        assert app.conf.beat_schedule["source-scan-daily"]["task"] == "featcat.tasks.sources.source_scan"
        assert app.conf.beat_schedule["baseline-refresh-weekly"]["task"] == "featcat.tasks.monitoring.baseline_refresh"

    def test_include_lists_all_task_modules(self) -> None:
        """Worker must auto-load every task module so beat dispatch
        actually finds a registered handler at runtime."""
        from featcat.tasks.app import app

        # Celery normalises ``include`` into ``conf.include``.
        assert "featcat.tasks.monitoring" in app.conf.include
        assert "featcat.tasks.docs" in app.conf.include
        assert "featcat.tasks.sources" in app.conf.include

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


class TestBaselineRefreshTask:
    def test_task_name_matches_route(self) -> None:
        from featcat.tasks.monitoring import baseline_refresh

        assert baseline_refresh.name == "featcat.tasks.monitoring.baseline_refresh"

    def test_runs_eagerly_calls_baseline_action(self, eager_celery: object) -> None:
        """The task must reuse MonitoringPlugin with action='baseline' so
        the in-process and Celery paths produce identical baselines."""
        from featcat.tasks import monitoring as mon_mod

        canned = mock.Mock(status="success", data={"baselines_saved": 4, "total_features": 4})
        plugin_cls = mock.Mock()
        plugin_cls.return_value.execute.return_value = canned

        with (
            mock.patch("featcat.plugins.monitoring.MonitoringPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
        ):
            backend = mock.Mock()
            get_backend.return_value = backend
            result = mon_mod.baseline_refresh.apply().get()

        assert result["status"] == "success"
        assert result["data"]["baselines_saved"] == 4
        backend.close.assert_called_once()
        plugin_cls.return_value.execute.assert_called_once()
        kwargs = plugin_cls.return_value.execute.call_args.kwargs
        assert kwargs.get("action") == "baseline"

    def test_baseline_refresh_does_not_require_llm(self, eager_celery: object) -> None:
        """Baselines are pure stats — the task must not crash when the
        LLM stack isn't even importable."""
        from featcat.tasks import monitoring as mon_mod

        canned = mock.Mock(status="success", data={})
        plugin_cls = mock.Mock()
        plugin_cls.return_value.execute.return_value = canned
        with (
            mock.patch("featcat.plugins.monitoring.MonitoringPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
        ):
            get_backend.return_value = mock.Mock()
            result = mon_mod.baseline_refresh.apply().get()
        assert result["status"] == "success"
        # Second positional arg is the LLM, which must be None for
        # baseline computation.
        assert plugin_cls.return_value.execute.call_args.args[1] is None


class TestDocGenerateTask:
    def test_task_name_matches_route(self) -> None:
        from featcat.tasks.docs import doc_generate

        assert doc_generate.name == "featcat.tasks.docs.doc_generate"

    def test_runs_autodoc_plugin(self, eager_celery: object) -> None:
        from featcat.tasks import docs as docs_mod

        canned = mock.Mock(status="success", data={"documented": 3})
        plugin_cls = mock.Mock()
        plugin_cls.return_value.execute.return_value = canned

        with (
            mock.patch("featcat.plugins.autodoc.AutodocPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
            mock.patch("featcat.llm.create_llm") as create_llm,
        ):
            backend = mock.Mock()
            get_backend.return_value = backend
            create_llm.return_value = mock.Mock()
            result = docs_mod.doc_generate.apply().get()

        assert result["status"] == "success"
        assert result["data"]["documented"] == 3
        backend.close.assert_called_once()
        plugin_cls.return_value.execute.assert_called_once()

    def test_skips_when_llm_unavailable(self, eager_celery: object) -> None:
        """Autodoc *needs* the LLM. Without it the task must return a
        skipped status instead of failing — same contract as the
        in-process scheduler's _run_doc_generate."""
        from featcat.tasks import docs as docs_mod

        plugin_cls = mock.Mock()
        with (
            mock.patch("featcat.plugins.autodoc.AutodocPlugin", plugin_cls),
            mock.patch("featcat.catalog.factory.get_backend") as get_backend,
            mock.patch("featcat.llm.create_llm", side_effect=RuntimeError("offline")),
        ):
            backend = mock.Mock()
            get_backend.return_value = backend
            result = docs_mod.doc_generate.apply().get()

        assert result["status"] == "skipped"
        assert result["data"]["documented"] == 0
        # Plugin should never run when LLM is unavailable.
        plugin_cls.return_value.execute.assert_not_called()
        backend.close.assert_called_once()


class TestSourceScanTask:
    def test_task_name_matches_route(self) -> None:
        from featcat.tasks.sources import source_scan

        assert source_scan.name == "featcat.tasks.sources.source_scan"

    def test_only_scans_auto_refresh_sources(self, eager_celery: object) -> None:
        """Mirror the scheduler's behaviour: sources with auto_refresh=0
        are listed but not scanned."""
        from featcat.tasks import sources as sources_mod

        # Two fake sources; only the first has auto_refresh=1.
        # IDs are strings — matches the catalog's UUID convention.
        src_on = mock.Mock(id="src-on", name="ds_on", path="/tmp/on")
        src_off = mock.Mock(id="src-off", name="ds_off", path="/tmp/off")

        backend = mock.MagicMock()
        backend.list_sources.return_value = [src_on, src_off]

        # Session.execute(...).first() drives the auto_refresh gate.
        # Two .first() calls happen — one per source row.
        session = mock.MagicMock()
        session.execute.side_effect = [
            mock.Mock(first=mock.Mock(return_value=(1,))),  # auto_refresh=1
            mock.Mock(first=mock.Mock(return_value=(0,))),  # auto_refresh=0
        ]
        backend.session.return_value.__enter__.return_value = session
        backend.session.return_value.__exit__.return_value = False

        fake_columns = [mock.Mock(column_name="age", dtype="int64", stats={"mean": 30})]

        with (
            mock.patch("featcat.catalog.factory.get_backend", return_value=backend),
            mock.patch("featcat.catalog.scanner.scan_source", return_value=fake_columns) as scan,
        ):
            result = sources_mod.source_scan.apply().get()

        assert result["status"] == "success"
        assert result["data"]["sources_scanned"] == 1
        assert result["data"]["features_updated"] == 1
        # Scanner must only have been called for the auto_refresh=1 source.
        scan.assert_called_once_with("/tmp/on")
        backend.upsert_feature.assert_called_once()
        backend.close.assert_called_once()


class TestSchedulerCeleryDispatch:
    """T1.5b wiring: when ``settings.tasks_backend == 'celery'``, the
    in-process FeatcatScheduler dispatches via send_task instead of
    running the plugin inline."""

    def test_dispatches_each_job_to_correct_celery_task(self) -> None:
        from featcat.config import Settings
        from featcat.server.scheduler import FeatcatScheduler

        backend = mock.Mock()
        settings = Settings(tasks_backend="celery")
        sched = FeatcatScheduler(backend=backend, llm=None, settings=settings)

        celery_app = mock.Mock()
        async_result = mock.Mock()
        async_result.get.return_value = {"status": "success", "data": {"k": "v"}, "task_id": "abc"}
        celery_app.send_task.return_value = async_result

        with mock.patch("featcat.tasks.app.app", celery_app):
            for job_name, expected in [
                ("monitor_check", "featcat.tasks.monitoring.monitor_check"),
                ("doc_generate", "featcat.tasks.docs.doc_generate"),
                ("source_scan", "featcat.tasks.sources.source_scan"),
                ("baseline_refresh", "featcat.tasks.monitoring.baseline_refresh"),
            ]:
                celery_app.send_task.reset_mock()
                summary = sched._dispatch_via_celery(job_name)
                celery_app.send_task.assert_called_once_with(expected)
                # Scheduler's run_job stores result_summary as a dict — the
                # Celery wrapper unwraps the worker's "data" field for us.
                assert summary == {"k": "v"}

    def test_apscheduler_path_unaffected_by_default(self) -> None:
        """The default settings keep tasks_backend='apscheduler', so
        _execute() must call the in-process helpers, never Celery."""
        import asyncio

        from featcat.config import Settings
        from featcat.server.scheduler import FeatcatScheduler

        backend = mock.Mock()
        settings = Settings()
        assert settings.tasks_backend == "apscheduler"

        sched = FeatcatScheduler(backend=backend, llm=None, settings=settings)

        with (
            mock.patch.object(sched, "_dispatch_via_celery") as dispatch,
            mock.patch.object(sched, "_run_monitor_check", return_value={"ok": True}) as inproc,
        ):
            asyncio.run(sched._execute("monitor_check"))

        dispatch.assert_not_called()
        inproc.assert_called_once()

    def test_unknown_job_raises_valueerror_in_celery_path(self) -> None:
        from featcat.config import Settings
        from featcat.server.scheduler import FeatcatScheduler

        sched = FeatcatScheduler(backend=mock.Mock(), llm=None, settings=Settings(tasks_backend="celery"))
        with (
            mock.patch("featcat.tasks.app.app", mock.Mock()),
            pytest.raises(ValueError, match="Unknown job"),
        ):
            sched._dispatch_via_celery("nope_not_a_job")
