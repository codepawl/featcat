"""Service-level tests for DB-backed materialization schedules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.materialization_scheduler import run_due_materialization_schedules
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.online_store import get_online_features

if TYPE_CHECKING:
    from pathlib import Path

    from featcat.catalog.materialization import MaterializationResult


NOW = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)


def _clock() -> datetime:
    return NOW


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> None:
    pq.write_table(pa.table(data), path)


def _backend(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    return db


def _seed_materialization_source(
    db: LocalBackend,
    tmp_path: Path,
    *,
    data: dict[str, list[Any]] | None = None,
    feature_columns: list[str] | None = None,
) -> None:
    parquet_path = tmp_path / "transactions.parquet"
    _write_parquet(
        parquet_path,
        data
        or {
            "customer_id": [1, 1, 2],
            "event_ts": [
                "2026-05-25T09:00:00Z",
                "2026-05-25T10:00:00Z",
                "2026-05-25T08:00:00Z",
            ],
            "avg_spend_30d": [10.0, 20.0, 30.0],
        },
    )
    source = DataSource(
        name="transactions",
        path=str(parquet_path),
        entity_key="customer_id",
        event_timestamp_column="event_ts",
    )
    db.add_source(source)
    for column in feature_columns or ["avg_spend_30d"]:
        db.upsert_feature(
            Feature(
                name=f"transactions.{column}",
                data_source_id=source.id,
                column_name=column,
                dtype="float64",
            )
        )


def _create_due_schedule(db: LocalBackend, *, enabled: bool = True, interval_seconds: int = 60) -> str:
    schedule = db.create_materialization_schedule(
        name="transactions-hourly",
        source_name="transactions",
        feature_columns=["avg_spend_30d"],
        project="churn",
        feature_view="transactions",
        interval_seconds=interval_seconds,
        enabled=enabled,
        next_run_at=NOW - timedelta(seconds=1),
        now=NOW - timedelta(minutes=10),
    )
    return schedule.id


def test_create_schedule_validates_missing_source_features_and_interval(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        with pytest.raises(ValueError, match="name is required"):
            db.create_materialization_schedule(
                name="",
                source_name="transactions",
                feature_columns=["avg_spend_30d"],
                interval_seconds=60,
                now=NOW,
            )
        with pytest.raises(ValueError, match="source_name is required"):
            db.create_materialization_schedule(
                name="bad-source",
                source_name="",
                feature_columns=["avg_spend_30d"],
                interval_seconds=60,
                now=NOW,
            )
        with pytest.raises(ValueError, match="feature_columns must be non-empty"):
            db.create_materialization_schedule(
                name="bad-features",
                source_name="transactions",
                feature_columns=[],
                interval_seconds=60,
                now=NOW,
            )
        with pytest.raises(ValueError, match="interval_seconds must be greater than 0"):
            db.create_materialization_schedule(
                name="bad-interval",
                source_name="transactions",
                feature_columns=["avg_spend_30d"],
                interval_seconds=0,
                now=NOW,
            )
        with pytest.raises(ValueError, match="schedule_type must be 'interval'"):
            db.create_materialization_schedule(
                name="bad-type",
                source_name="transactions",
                feature_columns=["avg_spend_30d"],
                interval_seconds=60,
                schedule_type="cron",
                now=NOW,
            )
    finally:
        db.close()


def test_interval_next_run_at_uses_injected_clock(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        schedule = db.create_materialization_schedule(
            name="transactions-hourly",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=300,
            now=NOW,
        )
    finally:
        db.close()

    assert schedule.next_run_at == NOW + timedelta(seconds=300)


def test_list_schedules_returns_newest_first_with_deterministic_tiebreak(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        db.create_materialization_schedule(
            name="older",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=60,
            now=NOW - timedelta(minutes=5),
        )
        db.create_materialization_schedule(
            name="newer-b",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=60,
            now=NOW,
        )
        db.create_materialization_schedule(
            name="newer-a",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=60,
            now=NOW,
        )
        schedules = db.list_materialization_schedules()
    finally:
        db.close()

    assert [schedule.name for schedule in schedules] == ["newer-a", "newer-b", "older"]


def test_disabled_schedule_is_not_claimed(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        _create_due_schedule(db, enabled=False)
        claimed = db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
    finally:
        db.close()

    assert claimed == []


def test_due_schedule_is_claimed(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        schedule_id = _create_due_schedule(db)
        claimed = db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
        schedule = db.get_materialization_schedule(schedule_id)
    finally:
        db.close()

    assert [schedule.id for schedule in claimed] == [schedule_id]
    assert schedule is not None
    assert schedule.lease_owner == "runner-1"
    assert schedule.lease_until == NOW + timedelta(minutes=5)


def test_non_due_schedule_is_skipped(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        db.create_materialization_schedule(
            name="future",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=60,
            next_run_at=NOW + timedelta(seconds=1),
            now=NOW,
        )
        claimed = db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
    finally:
        db.close()

    assert claimed == []


def test_two_runner_ids_cannot_claim_the_same_row(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        schedule_id = _create_due_schedule(db)
        first = db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
        second = db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-2",
            lease_until=NOW + timedelta(minutes=5),
        )
    finally:
        db.close()

    assert [schedule.id for schedule in first] == [schedule_id]
    assert second == []


def test_expired_lease_can_be_reclaimed(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        schedule_id = _create_due_schedule(db)
        db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
        claimed = db.claim_due_materialization_schedules(
            now=NOW + timedelta(minutes=5),
            lease_owner="runner-2",
            lease_until=NOW + timedelta(minutes=10),
        )
        schedule = db.get_materialization_schedule(schedule_id)
    finally:
        db.close()

    assert [item.id for item in claimed] == [schedule_id]
    assert schedule is not None
    assert schedule.lease_owner == "runner-2"


def test_successful_run_writes_online_values_and_audit_with_schedule_id(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        _seed_materialization_source(db, tmp_path)
        schedule_id = _create_due_schedule(db)
        result = run_due_materialization_schedules(db, runner_id="runner-1", clock=_clock)
        online = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}],
            feature_refs=["transactions.avg_spend_30d"],
            project="churn",
            feature_view="transactions",
        )
        audits = db.list_materialization_audits()
        schedule = db.get_materialization_schedule(schedule_id)
    finally:
        db.close()

    assert result.claimed == 1
    assert result.runs[0].status == "success"
    assert online.rows[0].features["transactions.avg_spend_30d"] == 20.0
    assert audits[0].status == "success"
    assert audits[0].schedule_id == schedule_id
    assert schedule is not None
    assert schedule.last_run_at == NOW
    assert schedule.next_run_at == NOW + timedelta(seconds=60)
    assert schedule.lease_owner is None
    assert schedule.lease_until is None


def test_validation_failure_writes_validation_failed_audit_with_schedule_id(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        _seed_materialization_source(
            db,
            tmp_path,
            data={
                "customer_id": [1],
                "event_ts": ["2026-05-25T10:00:00Z"],
            },
            feature_columns=["avg_spend_30d"],
        )
        schedule_id = _create_due_schedule(db)
        result = run_due_materialization_schedules(db, runner_id="runner-1", clock=_clock)
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert result.runs[0].status == "validation_failed"
    assert audits[0].status == "validation_failed"
    assert audits[0].schedule_id == schedule_id
    assert audits[0].errors[0]["code"] == "missing_feature_column"


def test_unexpected_error_writes_error_audit_and_clears_lease(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _backend(tmp_path)

    def raise_boom(*args: object, **kwargs: object) -> MaterializationResult:
        raise RuntimeError("boom")

    monkeypatch.setattr("featcat.catalog.materialization_scheduler.materialize_latest_from_source", raise_boom)
    try:
        _seed_materialization_source(db, tmp_path)
        schedule_id = _create_due_schedule(db)
        result = run_due_materialization_schedules(db, runner_id="runner-1", clock=_clock)
        audits = db.list_materialization_audits()
        schedule = db.get_materialization_schedule(schedule_id)
    finally:
        db.close()

    assert result.runs[0].status == "error"
    assert audits[0].status == "error"
    assert audits[0].schedule_id == schedule_id
    assert audits[0].errors == [{"code": "materialization_error", "message": "boom", "field": None}]
    assert schedule is not None
    assert schedule.lease_owner is None
    assert schedule.lease_until is None


def test_finish_run_advances_next_run_at_and_clears_lease(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        schedule_id = _create_due_schedule(db, interval_seconds=120)
        db.claim_due_materialization_schedules(
            now=NOW,
            lease_owner="runner-1",
            lease_until=NOW + timedelta(minutes=5),
        )
        schedule = db.finish_materialization_schedule_run(
            schedule_id,
            finished_at=NOW + timedelta(seconds=10),
            next_run_at=NOW + timedelta(seconds=130),
            lease_owner="runner-1",
        )
    finally:
        db.close()

    assert schedule is not None
    assert schedule.last_run_at == NOW + timedelta(seconds=10)
    assert schedule.next_run_at == NOW + timedelta(seconds=130)
    assert schedule.lease_owner is None
    assert schedule.lease_until is None
