"""Tests for ``featcat.diagnostics.runner`` — registry + timeout + aggregation.

These tests swap out the runner's module-level ``_REGISTRY`` per test so the
shared registry isn't polluted by fake checks. Real check registrations live
in ``checks_*.py`` modules that aren't imported here.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from featcat.config import Settings
from featcat.diagnostics import (
    AggregateReport,
    CheckResult,
    CheckStatus,
    aggregate,
    register,
    run_all,
    run_group,
)
from featcat.diagnostics import runner as runner_mod

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture()
def fresh_registry(monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, list], None, None]:
    """Give each test an empty registry shadow so registrations don't leak."""
    clean: dict[str, list] = {g: [] for g in runner_mod.GROUPS}
    monkeypatch.setattr(runner_mod, "_REGISTRY", clean)
    yield clean


@pytest.fixture()
def settings() -> Settings:
    return Settings()


def _passing_check(_: Settings) -> CheckResult:
    return CheckResult(name="ok", status=CheckStatus.PASS, detail="all good")


def _failing_check(_: Settings) -> CheckResult:
    return CheckResult(name="broken", status=CheckStatus.FAIL, detail="nope", resolution="fix it")


def _raising_check(_: Settings) -> CheckResult:
    raise RuntimeError("kaboom")


def _slow_check(_: Settings) -> CheckResult:
    time.sleep(0.5)
    return CheckResult(name="slow", status=CheckStatus.PASS)


def _warn_check(_: Settings) -> CheckResult:
    return CheckResult(name="meh", status=CheckStatus.WARN, detail="suboptimal")


def _skip_check(_: Settings) -> CheckResult:
    return CheckResult(name="absent", status=CheckStatus.SKIP, detail="context missing")


class TestRegistry:
    def test_register_adds_to_named_group(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        assert _passing_check in fresh_registry["db"]

    def test_register_rejects_unknown_group(self, fresh_registry: dict) -> None:
        with pytest.raises(ValueError, match="Unknown group"):
            register("ghost", _passing_check)


class TestRunGroup:
    def test_runs_registered_checks(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        register("db", _failing_check)

        report = run_group("db", settings=settings)
        assert report.group == "db"
        assert len(report.checks) == 2
        names = {c.name for c in report.checks}
        assert names == {"ok", "broken"}

    def test_empty_group_returns_empty_checks(self, fresh_registry: dict, settings: Settings) -> None:
        report = run_group("llm", settings=settings)
        assert report.group == "llm"
        assert report.checks == []

    def test_raising_check_becomes_fail(self, fresh_registry: dict, settings: Settings) -> None:
        """A check that raises must not crash the runner — it should be reported as FAIL."""
        register("db", _raising_check)
        report = run_group("db", settings=settings)
        assert len(report.checks) == 1
        result = report.checks[0]
        assert result.status is CheckStatus.FAIL
        assert "kaboom" in result.detail
        assert result.name == "_raising_check"

    def test_unknown_group_raises(self, fresh_registry: dict, settings: Settings) -> None:
        with pytest.raises(ValueError, match="Unknown group"):
            run_group("ghost", settings=settings)

    def test_duration_filled_when_check_omits_it(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        report = run_group("db", settings=settings)
        assert report.checks[0].duration_ms >= 0  # filled by runner when check returns 0

    def test_check_provided_duration_preserved(self, fresh_registry: dict, settings: Settings) -> None:
        def _explicit(_: Settings) -> CheckResult:
            return CheckResult(name="explicit", status=CheckStatus.PASS, duration_ms=999)

        register("db", _explicit)
        report = run_group("db", settings=settings)
        assert report.checks[0].duration_ms == 999


class TestRunGroupTimeout:
    def test_slow_check_becomes_fail(self, fresh_registry: dict, settings: Settings) -> None:
        """Any check exceeding the wall-clock budget is reported as FAIL with a timeout message."""
        register("db", _slow_check)
        report = run_group("db", timeout_per_check=0.05, settings=settings)
        assert len(report.checks) == 1
        result = report.checks[0]
        assert result.status is CheckStatus.FAIL
        assert "timed out" in result.detail.lower()
        assert result.name == "_slow_check"


class TestRunAll:
    def test_returns_one_report_per_group(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        register("llm", _passing_check)

        reports = run_all(settings=settings)
        assert set(reports) == set(runner_mod.GROUPS)
        assert len(reports["db"].checks) == 1
        assert len(reports["llm"].checks) == 1
        assert reports["network"].checks == []

    def test_parallel_execution_under_budget(self, fresh_registry: dict, settings: Settings) -> None:
        """8 slow checks (0.3s each) must finish in well under 8*0.3=2.4s thanks to the thread pool."""
        for _ in range(8):
            register("db", _slow_check)

        started = time.monotonic()
        run_all(timeout_per_check=2.0, settings=settings)
        elapsed = time.monotonic() - started
        # With pool size 8 and 8 checks of 0.5s, we expect ~0.5s + overhead — give plenty of slack.
        assert elapsed < 1.5, f"expected parallel execution; took {elapsed:.2f}s"


class TestAggregate:
    def test_summary_counts_each_status(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        register("db", _failing_check)
        register("llm", _warn_check)
        register("deploy", _skip_check)

        reports = run_all(settings=settings)
        agg = aggregate(reports)
        assert isinstance(agg, AggregateReport)
        assert agg.summary == {"pass": 1, "warn": 1, "fail": 1, "skip": 1}

    def test_exit_code_one_when_any_fail(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        register("db", _failing_check)
        agg = aggregate(run_all(settings=settings))
        assert agg.exit_code == 1

    def test_exit_code_zero_when_no_fail(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        register("llm", _warn_check)
        register("deploy", _skip_check)
        agg = aggregate(run_all(settings=settings))
        # WARN and SKIP never cause non-zero exit.
        assert agg.exit_code == 0

    def test_version_is_one(self, fresh_registry: dict, settings: Settings) -> None:
        agg = aggregate(run_all(settings=settings))
        assert agg.version == 1

    def test_groups_passed_through(self, fresh_registry: dict, settings: Settings) -> None:
        register("db", _passing_check)
        reports = run_all(settings=settings)
        agg = aggregate(reports)
        assert set(agg.groups) == set(runner_mod.GROUPS)
        assert agg.groups["db"].checks[0].name == "ok"
