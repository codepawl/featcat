"""Diagnostics runner — registry + bounded-concurrency executor.

Checks register themselves via ``register("group", fn)`` at module import.
``run_group`` and ``run_all`` execute checks in a ``ThreadPoolExecutor`` and
enforce a per-check wall-clock timeout. ``run_all`` flattens across groups so
the aggregate budget (≤10s for all checks) doesn't pile up linearly per group.

A check function signature is ``Callable[[Settings], CheckResult]``. The runner
passes ``Settings`` to every check so individual checks stay pure and testable
(no global state, no env reads inside the check body).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING

from .models import AggregateReport, CheckResult, CheckStatus, GroupReport

if TYPE_CHECKING:
    from featcat.config import Settings

GROUPS: tuple[str, ...] = ("deploy", "db", "llm", "network", "data")

CheckFn = Callable[["Settings"], CheckResult]

_REGISTRY: dict[str, list[CheckFn]] = {g: [] for g in GROUPS}


def register(group: str, fn: CheckFn) -> CheckFn:
    """Add ``fn`` to ``group``'s check list. Returns ``fn`` for decorator use."""
    if group not in _REGISTRY:
        raise ValueError(f"Unknown group {group!r}. Known: {sorted(_REGISTRY)}")
    _REGISTRY[group].append(fn)
    return fn


def _ensure_settings(settings: Settings | None) -> Settings:
    if settings is not None:
        return settings
    from featcat.config import load_settings

    return load_settings()


def _run_one(fn: CheckFn, settings: Settings) -> CheckResult:
    """Run a single check with timing + exception capture.

    The future-level timeout still owns hard cut-off; this only handles
    raised exceptions and fills in ``duration_ms`` when a check didn't.
    """
    started = time.monotonic()
    try:
        result = fn(settings)
    except Exception as exc:  # noqa: BLE001 — diagnostics swallow check-level errors deliberately
        elapsed = int((time.monotonic() - started) * 1000)
        return CheckResult(
            name=fn.__name__,
            status=CheckStatus.FAIL,
            detail=f"check raised: {exc}",
            duration_ms=elapsed,
        )
    if result.duration_ms == 0:
        elapsed = int((time.monotonic() - started) * 1000)
        return result.model_copy(update={"duration_ms": elapsed})
    return result


def _execute(
    items: list[tuple[str, CheckFn]],
    timeout_per_check: float,
    settings: Settings,
) -> dict[str, list[CheckResult]]:
    """Run a flat list of (group, fn) tuples and bucket results back per group."""
    grouped: dict[str, list[CheckResult]] = {g: [] for g in _REGISTRY}
    if not items:
        return grouped

    with ThreadPoolExecutor(max_workers=min(8, len(items))) as ex:
        futures = [(group, fn, ex.submit(_run_one, fn, settings)) for group, fn in items]
        for group, fn, fut in futures:
            try:
                grouped[group].append(fut.result(timeout=timeout_per_check))
            except FutureTimeoutError:
                grouped[group].append(
                    CheckResult(
                        name=fn.__name__,
                        status=CheckStatus.FAIL,
                        detail=f"timed out after {timeout_per_check:.1f}s",
                        duration_ms=int(timeout_per_check * 1000),
                    )
                )
    return grouped


def run_group(
    name: str,
    *,
    timeout_per_check: float = 2.0,
    settings: Settings | None = None,
) -> GroupReport:
    """Run every check registered for ``name`` and return the per-group report."""
    if name not in _REGISTRY:
        raise ValueError(f"Unknown group {name!r}. Known: {sorted(_REGISTRY)}")
    settings = _ensure_settings(settings)
    items = [(name, fn) for fn in _REGISTRY[name]]
    grouped = _execute(items, timeout_per_check, settings)
    return GroupReport(group=name, checks=grouped[name])


def run_all(
    *,
    timeout_per_check: float = 2.0,
    settings: Settings | None = None,
) -> dict[str, GroupReport]:
    """Run every registered check across all groups in a single thread pool."""
    settings = _ensure_settings(settings)
    items: list[tuple[str, CheckFn]] = []
    for group, fns in _REGISTRY.items():
        for fn in fns:
            items.append((group, fn))
    grouped = _execute(items, timeout_per_check, settings)
    return {g: GroupReport(group=g, checks=grouped[g]) for g in _REGISTRY}


def aggregate(reports: dict[str, GroupReport]) -> AggregateReport:
    """Fold per-group reports into the JSON envelope the CLI / API emit.

    Exit code is 1 if any check is ``FAIL``, else 0. ``WARN`` and ``SKIP``
    never cause non-zero exits.
    """
    summary = {s.value: 0 for s in CheckStatus}
    for group_report in reports.values():
        for check in group_report.checks:
            summary[check.status.value] += 1
    exit_code = 1 if summary[CheckStatus.FAIL.value] > 0 else 0
    return AggregateReport(version=1, summary=summary, exit_code=exit_code, groups=reports)
