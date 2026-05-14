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

from . import checks_data as _checks_data  # noqa: F401 — registers data checks at import
from . import checks_db as _checks_db  # noqa: F401 — registers db checks at import
from . import checks_deploy as _checks_deploy  # noqa: F401 — registers deploy checks at import
from . import checks_llm as _checks_llm  # noqa: F401 — registers llm checks at import
from . import checks_network as _checks_network  # noqa: F401 — registers network checks at import
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
