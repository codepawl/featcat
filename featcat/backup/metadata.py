"""Pydantic models for the backup envelope and per-table manifest."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs the type at runtime.
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BACKUP_VERSION = 1


class BackupMetadata(BaseModel):
    """Top-level envelope serialized as ``metadata.json``."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = Field(default=1)
    featcat_version: str
    backend: Literal["sqlite", "postgres"]
    backend_version: str
    alembic_version: str | None
    created_at: datetime
    stats: dict[str, int]
    embedding_model: str | None


class BackupManifest(BaseModel):
    """Per-table inventory serialized as ``manifest.json``.

    ``table_order`` is the FK-respecting insertion order used at restore
    time. ``row_counts`` lets the CLI report the inventory without parsing
    every JSONL file.
    """

    model_config = ConfigDict(extra="forbid")

    table_order: list[str]
    row_counts: dict[str, int]
