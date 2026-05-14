"""Diagnostics module — shared check infrastructure for `featcat doctor` and `/api/health`.

Public surface:

- ``CheckResult``, ``CheckStatus``, ``GroupReport``, ``AggregateReport`` — payload types.
- ``register(group, fn)`` — decorator-style registration for individual checks.
- ``run_group(name)`` / ``run_all()`` — execute checks with bounded concurrency + per-check timeout.
- ``aggregate(reports)`` — fold ``run_all`` output into the JSON envelope the CLI / API emit.

Per-group check modules (``checks_db``, ``checks_llm``, …) register themselves at import time.
The top-level CLI and ``/api/health`` only need ``run_*`` + ``aggregate``.
"""

from __future__ import annotations

from .models import AggregateReport, CheckResult, CheckStatus, GroupReport
from .runner import GROUPS, aggregate, register, run_all, run_group

__all__ = [
    "GROUPS",
    "AggregateReport",
    "CheckResult",
    "CheckStatus",
    "GroupReport",
    "aggregate",
    "register",
    "run_all",
    "run_group",
]
