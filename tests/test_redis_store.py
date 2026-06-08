"""Redis online store behavior without requiring a live Redis server."""

from __future__ import annotations

from typing import Any

from featcat.catalog.models import OnlineFeatureWrite
from featcat.catalog.redis_store import get_online_features_redis, write_online_features_redis


class _FakePipeline:
    def __init__(self, store: dict[str, dict[str, str]]) -> None:
        self.store = store
        self.ops: list[tuple[str, str, dict[str, str] | None]] = []

    def hgetall(self, key: str) -> None:
        self.ops.append(("hgetall", key, None))

    def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        self.ops.append(("hset", key, mapping))

    def execute(self) -> list[dict[str, str]] | list[bool]:
        results: list[dict[str, str] | bool] = []
        for op, key, mapping in self.ops:
            if op == "hgetall":
                results.append(dict(self.store.get(key, {})))
            else:
                assert mapping is not None
                self.store[key] = dict(mapping)
                results.append(True)
        self.ops.clear()
        return results


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, str]] = {}

    def pipeline(self, *, transaction: bool = False) -> _FakePipeline:
        assert transaction is False
        return _FakePipeline(self.store)


def _write(**overrides: Any) -> OnlineFeatureWrite:
    return OnlineFeatureWrite(
        entity_key=overrides.pop("entity_key", {"customer_id": 1}),
        feature_ref=overrides.pop("feature_ref", "transactions.avg_spend_30d"),
        value=overrides.pop("value", 10.0),
        event_timestamp=overrides.pop("event_timestamp", "2026-05-25T10:00:00Z"),
        **overrides,
    )


def test_redis_online_store_writes_and_reads_ordered_features() -> None:
    redis = _FakeRedis()

    write_result = write_online_features_redis(
        redis,
        rows=[
            _write(entity_key={"customer_id": 1}, value=10.0),
            _write(entity_key={"customer_id": 2}, value=20.0),
        ],
        project="prod",
        feature_view="transactions",
    )
    read_result = get_online_features_redis(
        redis,
        entity_keys=[{"customer_id": 2}, {"customer_id": 1}],
        feature_refs=["transactions.avg_spend_30d"],
        project="prod",
        feature_view="transactions",
    )

    assert write_result.written == 2
    assert [row.features["transactions.avg_spend_30d"] for row in read_result.rows] == [20.0, 10.0]
    assert all(row.metadata["transactions.avg_spend_30d"].found for row in read_result.rows)


def test_redis_online_store_uses_same_timestamp_conflict_resolution() -> None:
    redis = _FakeRedis()

    first = write_online_features_redis(
        redis,
        rows=[_write(value=10.0, event_timestamp="2026-05-25T10:00:00Z")],
    )
    older = write_online_features_redis(
        redis,
        rows=[_write(value=5.0, event_timestamp="2026-05-25T09:00:00Z")],
    )
    newer = write_online_features_redis(
        redis,
        rows=[_write(value=20.0, event_timestamp="2026-05-25T11:00:00Z")],
    )

    read_result = get_online_features_redis(
        redis,
        entity_keys=[{"customer_id": 1}],
        feature_refs=["transactions.avg_spend_30d"],
    )

    assert first.written == 1
    assert older.skipped_older == 1
    assert newer.written == 1
    assert read_result.rows[0].features["transactions.avg_spend_30d"] == 20.0
