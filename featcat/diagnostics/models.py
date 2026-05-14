"""Payload types for the diagnostics module.

Kept deliberately small: a check returns a ``CheckResult``; a group of checks
yields a ``GroupReport``; the aggregate of all groups is an ``AggregateReport``.
The CLI's rich formatter and the JSON renderer both consume the same types.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CheckStatus(str, Enum):
    """Status of a single check.

    ``SKIP`` exists because some checks (Git in an installed-package context,
    Docker without a mounted socket, Alembic on the SQLite path) just don't
    apply to every deployment — flagging them as ``FAIL`` would page the wrong
    user. ``SKIP`` never causes a non-zero exit code.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckResult(BaseModel):
    """Single check outcome.

    ``resolution`` should be a concrete next step (a CLI command, a file
    path, or a short instruction) for ``WARN`` and ``FAIL`` rows. ``PASS``
    and ``SKIP`` typically leave it null.
    """

    name: str
    status: CheckStatus
    detail: str = ""
    resolution: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroupReport(BaseModel):
    group: str
    checks: list[CheckResult] = Field(default_factory=list)


class AggregateReport(BaseModel):
    """Top-level envelope emitted by ``featcat doctor --json``.

    Schema versioned via ``version`` so clients can detect breaking changes
    without parsing the whole tree.
    """

    version: int = 1
    summary: dict[str, int]
    exit_code: int
    groups: dict[str, GroupReport]
