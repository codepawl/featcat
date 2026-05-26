"""Explicit runner service for DB-backed materialization schedules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .materialization import materialize_latest_from_source
from .materialization_audit import record_materialization_audit, record_materialization_error_audit

if TYPE_CHECKING:
    from .backend import CatalogBackend


Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def next_interval_run(base: datetime, interval_seconds: int) -> datetime:
    return base + timedelta(seconds=interval_seconds)


@dataclass(frozen=True)
class MaterializationScheduleRunRecord:
    schedule_id: str
    schedule_name: str
    status: str
    audit_id: str


@dataclass(frozen=True)
class MaterializationSchedulerRunResult:
    runner_id: str
    claimed: int
    runs: list[MaterializationScheduleRunRecord] = field(default_factory=list)


def run_due_materialization_schedules(
    db: CatalogBackend,
    *,
    runner_id: str,
    clock: Clock = utcnow,
    lease_seconds: int = 1800,
    limit: int = 10,
) -> MaterializationSchedulerRunResult:
    """Claim and execute due interval materialization schedules once.

    This is intentionally a one-shot service. A CLI or lab process can call it
    repeatedly later without requiring FastAPI startup tasks or external schedulers.
    """
    now = clock()
    claimed = db.claim_due_materialization_schedules(
        now=now,
        lease_owner=runner_id,
        lease_until=now + timedelta(seconds=lease_seconds),
        limit=limit,
    )
    records: list[MaterializationScheduleRunRecord] = []
    for schedule in claimed:
        try:
            result = materialize_latest_from_source(
                db,
                source_name=schedule.source_name,
                feature_columns=schedule.feature_columns,
                project=schedule.project,
                feature_view=schedule.feature_view,
            )
            audit_id = record_materialization_audit(
                db,
                result=result,
                actor=schedule.actor,
                schedule_id=schedule.id,
            )
            status = "success" if result.is_valid else "validation_failed"
        except Exception as exc:
            audit_id = record_materialization_error_audit(
                db,
                source_name=schedule.source_name,
                project=schedule.project,
                feature_view=schedule.feature_view,
                feature_columns=schedule.feature_columns,
                error=exc,
                actor=schedule.actor,
                schedule_id=schedule.id,
            )
            status = "error"
        finally:
            finished_at = clock()
            db.finish_materialization_schedule_run(
                schedule.id,
                finished_at=finished_at,
                next_run_at=next_interval_run(finished_at, schedule.interval_seconds),
                lease_owner=runner_id,
            )
        records.append(
            MaterializationScheduleRunRecord(
                schedule_id=schedule.id,
                schedule_name=schedule.name,
                status=status,
                audit_id=audit_id,
            )
        )
    return MaterializationSchedulerRunResult(runner_id=runner_id, claimed=len(claimed), runs=records)


def run_materialization_schedule_once(
    db: CatalogBackend,
    *,
    schedule_id: str,
    clock: Clock = utcnow,
) -> MaterializationScheduleRunRecord | None:
    """Execute one materialization schedule immediately."""
    schedule = db.get_materialization_schedule(schedule_id)
    if schedule is None:
        return None

    try:
        result = materialize_latest_from_source(
            db,
            source_name=schedule.source_name,
            feature_columns=schedule.feature_columns,
            project=schedule.project,
            feature_view=schedule.feature_view,
        )
        audit_id = record_materialization_audit(
            db,
            result=result,
            actor=schedule.actor,
            schedule_id=schedule.id,
        )
        status = "success" if result.is_valid else "validation_failed"
    except Exception as exc:
        audit_id = record_materialization_error_audit(
            db,
            source_name=schedule.source_name,
            project=schedule.project,
            feature_view=schedule.feature_view,
            feature_columns=schedule.feature_columns,
            error=exc,
            actor=schedule.actor,
            schedule_id=schedule.id,
        )
        status = "error"
    finally:
        finished_at = clock()
        db.finish_materialization_schedule_run(
            schedule.id,
            finished_at=finished_at,
            next_run_at=next_interval_run(finished_at, schedule.interval_seconds),
        )

    return MaterializationScheduleRunRecord(
        schedule_id=schedule.id,
        schedule_name=schedule.name,
        status=status,
        audit_id=audit_id,
    )
