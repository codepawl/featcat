"""Tests for FeatCatClient.

Uses ``httpx.MockTransport`` to inject server responses without a live server.
A dispatcher inspects ``request.url.path`` + method and returns the right
``httpx.Response``. Test scope mirrors the public API surface plus the retry
and error-wrapping invariants.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from featcat_client import (
    ConnectionError,
    DataSource,
    FeatCatClient,
    Feature,
    FeatureGroupDetail,
    FeatureNotFound,
    GroupNotFound,
    OnlineFeatureReadResult,
    OnlineFeatureWriteResult,
    ServerError,
    TrainingDatasetBuildAudit,
    TrainingDatasetBuildResult,
)


def _client_with_handler(handler: Any) -> FeatCatClient:
    transport = httpx.MockTransport(handler)
    return FeatCatClient(base_url="http://server.test", actor="test-actor", transport=transport)


# --------------------------------------------------------------------------- #
# Sources / Features / Search                                                 #
# --------------------------------------------------------------------------- #


def test_list_features_passes_filters(feature_payload: dict[str, Any]) -> None:
    seen_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/features"
        seen_params.update(request.url.params)
        return httpx.Response(200, json=[feature_payload])

    with _client_with_handler(handler) as client:
        feats = client.list_features(source="user_behavior", tag="churn", dtype="int64")
    assert len(feats) == 1
    assert isinstance(feats[0], Feature)
    assert feats[0].name == "user_behavior.session_count_30d"
    assert seen_params["source"] == "user_behavior"
    assert seen_params["tag"] == "churn"
    assert seen_params["dtype"] == "int64"


def test_list_sources_preserves_join_metadata(source_payload: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/sources"
        return httpx.Response(200, json=[source_payload])

    with _client_with_handler(handler) as client:
        sources = client.list_sources()

    assert len(sources) == 1
    assert isinstance(sources[0], DataSource)
    assert sources[0].entity_key == "user_id"
    assert sources[0].event_timestamp_column == "event_ts"
    assert sources[0].created_timestamp_column == "created_at"


def test_get_feature_404_raises_feature_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Feature not found: xyz"})

    with _client_with_handler(handler) as client, pytest.raises(FeatureNotFound) as exc_info:
        client.get_feature("xyz")
    assert exc_info.value.name == "xyz"


def test_get_feature_strips_server_enrichments(feature_payload: dict[str, Any]) -> None:
    """``extra="ignore"`` on the model means health_score/has_doc don't break parsing."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=feature_payload)

    with _client_with_handler(handler) as client:
        feat = client.get_feature("user_behavior.session_count_30d")
    assert feat.id == "f-uuid-1"
    assert "health_score" not in feat.model_dump()


def test_actor_header_sent(feature_payload: dict[str, Any]) -> None:
    captured: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("X-Featcat-Actor"))
        return httpx.Response(200, json=feature_payload)

    with _client_with_handler(handler) as client:
        client.get_feature("x")
    assert captured == ["test-actor"]


def test_search_uses_features_endpoint(feature_payload: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/features"
        assert request.url.params.get("search") == "session count"
        return httpx.Response(200, json=[feature_payload])

    with _client_with_handler(handler) as client:
        results = client.search("session count")
    assert len(results) == 1


def test_find_similar_filters_graph_to_target(feature_payload: dict[str, Any]) -> None:
    """find_similar walks the similarity-graph response and filters edges incident on ``name``."""
    other = dict(feature_payload, id="f-uuid-2", name="user_behavior.event_count_30d", column_name="event_count_30d")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/features/similarity-graph":
            edges = [
                {
                    "source": "user_behavior.session_count_30d",
                    "target": "user_behavior.event_count_30d",
                    "similarity": 0.78,
                },
                {"source": "other.x", "target": "other.y", "similarity": 0.9},
            ]
            return httpx.Response(200, json={"nodes": [], "edges": edges})
        if request.url.path == "/api/features/by-name":
            return httpx.Response(200, json=other)
        return httpx.Response(404)

    with _client_with_handler(handler) as client:
        sim = client.find_similar("user_behavior.session_count_30d", top_k=5)
    assert [f.name for f in sim] == ["user_behavior.event_count_30d"]


# --------------------------------------------------------------------------- #
# Groups                                                                      #
# --------------------------------------------------------------------------- #


def test_get_group_404_raises_group_not_found() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    with _client_with_handler(handler) as client, pytest.raises(GroupNotFound):
        client.get_group("nope")


def test_get_group_returns_detail_with_members(group_payload: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/groups/churn_v2"
        return httpx.Response(200, json=group_payload)

    with _client_with_handler(handler) as client:
        detail = client.get_group("churn_v2")
    assert isinstance(detail, FeatureGroupDetail)
    assert detail.group.name == "churn_v2"
    assert len(detail.members) == 1
    assert detail.members[0].name == "user_behavior.session_count_30d"


# --------------------------------------------------------------------------- #
# Retry + error mapping                                                        #
# --------------------------------------------------------------------------- #


def test_retries_on_5xx_then_succeeds(feature_payload: dict[str, Any]) -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"detail": "down"})
        return httpx.Response(200, json=feature_payload)

    with _client_with_handler(handler) as client:
        feat = client.get_feature("x")
    assert calls["n"] == 3
    assert feat.name == "user_behavior.session_count_30d"


def test_5xx_after_retries_raises_server_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "permanent"})

    with _client_with_handler(handler) as client, pytest.raises(ServerError) as exc_info:
        client.get_feature("x")
    assert exc_info.value.status_code == 503
    assert exc_info.value.body == {"detail": "permanent"}


def test_network_error_wraps_to_connection_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS resolution failed")

    with _client_with_handler(handler) as client, pytest.raises(ConnectionError):
        client.get_feature("x")


def test_get_path_resolves_via_sources(feature_payload: dict[str, Any], source_payload: dict[str, Any]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/features/by-name":
            return httpx.Response(200, json=feature_payload)
        if request.url.path == "/api/sources":
            return httpx.Response(200, json=[source_payload])
        return httpx.Response(404)

    with _client_with_handler(handler) as client:
        path = client.get_path("user_behavior.session_count_30d")
    assert path == "/data/user_behavior.parquet"


# --------------------------------------------------------------------------- #
# Training datasets                                                           #
# --------------------------------------------------------------------------- #


def _dataset_success_payload() -> dict[str, Any]:
    return {
        "is_valid": True,
        "errors": [],
        "warnings": [],
        "entity_df_path": "labels.parquet",
        "source_path": "features.parquet",
        "entity_key": "customer_id",
        "entity_timestamp_column": "event_ts",
        "source_event_timestamp_column": "feature_ts",
        "feature_columns": ["avg_spend_30d", "txn_count_30d"],
        "output_path": "training.parquet",
        "row_count": 10,
        "feature_count": 2,
        "unresolved_row_count": 1,
        "missing_feature_value_count": 2,
    }


def _dataset_audit_payload() -> dict[str, Any]:
    return {
        "id": "audit-1",
        "status": "success",
        "entity_df_path": "labels.parquet",
        "source_path": "features.parquet",
        "source_name": None,
        "output_path": "training.parquet",
        "entity_key": "customer_id",
        "entity_timestamp_column": "event_ts",
        "source_event_timestamp_column": "feature_ts",
        "feature_columns": ["avg_spend_30d", "txn_count_30d"],
        "row_count": 10,
        "feature_count": 2,
        "unresolved_row_count": 1,
        "missing_feature_value_count": 2,
        "errors": [],
        "warnings": [],
        "actor": "api",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def test_build_training_dataset_posts_expected_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_dataset_success_payload())

    with _client_with_handler(handler) as client:
        result = client.build_training_dataset(
            entity_df_path="labels.parquet",
            source_path="features.parquet",
            entity_key="customer_id",
            entity_timestamp_column="event_ts",
            source_event_timestamp_column="feature_ts",
            feature_columns=["avg_spend_30d", "txn_count_30d"],
            output_path="training.parquet",
        )

    assert isinstance(result, TrainingDatasetBuildResult)
    assert captured == {
        "method": "POST",
        "path": "/api/datasets/build",
        "body": {
            "entity_df_path": "labels.parquet",
            "source_path": "features.parquet",
            "entity_key": "customer_id",
            "entity_timestamp_column": "event_ts",
            "source_event_timestamp_column": "feature_ts",
            "feature_columns": ["avg_spend_30d", "txn_count_30d"],
            "output_path": "training.parquet",
        },
    }


def test_build_training_dataset_parses_success_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_dataset_success_payload())

    with _client_with_handler(handler) as client:
        result = client.build_training_dataset(
            entity_df_path="labels.parquet",
            source_path="features.parquet",
            entity_key="customer_id",
            entity_timestamp_column="event_ts",
            source_event_timestamp_column="feature_ts",
            feature_columns=["avg_spend_30d", "txn_count_30d"],
            output_path="training.parquet",
        )

    assert result.is_valid is True
    assert result.row_count == 10
    assert result.feature_count == 2
    assert result.unresolved_row_count == 1
    assert result.output_path == "training.parquet"


def test_build_training_dataset_parses_validation_failure_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                **_dataset_success_payload(),
                "is_valid": False,
                "errors": [
                    {
                        "code": "source_dataframe_missing_entity_key",
                        "message": "Source dataframe is missing entity key column: customer_id",
                        "field": "entity_key",
                    }
                ],
                "output_path": None,
                "row_count": 0,
            },
        )

    with _client_with_handler(handler) as client:
        result = client.build_training_dataset(
            entity_df_path="labels.parquet",
            source_path="features.parquet",
            entity_key="customer_id",
            entity_timestamp_column="event_ts",
            source_event_timestamp_column="feature_ts",
            feature_columns=["avg_spend_30d"],
            output_path="training.parquet",
        )

    assert result.is_valid is False
    assert result.errors[0].code == "source_dataframe_missing_entity_key"
    assert result.errors[0].field == "entity_key"
    assert result.output_path is None


def test_build_training_dataset_supports_source_name() -> None:
    captured_body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content))
        return httpx.Response(200, json={**_dataset_success_payload(), "source_path": "/data/features.parquet"})

    with _client_with_handler(handler) as client:
        result = client.build_training_dataset(
            entity_df_path="labels.parquet",
            source_name="registered_features",
            entity_timestamp_column="event_ts",
            feature_columns=["avg_spend_30d"],
        )

    assert captured_body == {
        "entity_df_path": "labels.parquet",
        "feature_columns": ["avg_spend_30d"],
        "source_name": "registered_features",
        "entity_timestamp_column": "event_ts",
    }
    assert result.source_path == "/data/features.parquet"


def test_list_training_dataset_builds_sends_expected_request() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=[_dataset_audit_payload()])

    with _client_with_handler(handler) as client:
        rows = client.list_training_dataset_builds(limit=20, status="success")

    assert isinstance(rows[0], TrainingDatasetBuildAudit)
    assert captured == {
        "method": "GET",
        "path": "/api/datasets/builds",
        "params": {"limit": "20", "status": "success"},
    }


def test_list_training_dataset_builds_parses_response() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                _dataset_audit_payload(),
                {
                    **_dataset_audit_payload(),
                    "id": "audit-2",
                    "status": "validation_failed",
                    "errors": [
                        {
                            "code": "source_dataframe_missing_entity_key",
                            "message": "Source dataframe is missing entity key column: customer_id",
                            "field": "entity_key",
                        }
                    ],
                },
            ],
        )

    with _client_with_handler(handler) as client:
        rows = client.list_training_dataset_builds()

    assert [row.id for row in rows] == ["audit-1", "audit-2"]
    assert rows[0].status == "success"
    assert rows[0].feature_columns == ["avg_spend_30d", "txn_count_30d"]
    assert rows[1].status == "validation_failed"
    assert rows[1].errors[0].code == "source_dataframe_missing_entity_key"


# --------------------------------------------------------------------------- #
# Online store                                                                #
# --------------------------------------------------------------------------- #


def _online_write_result_payload() -> dict[str, Any]:
    return {
        "requested": 1,
        "written": 1,
        "skipped_older": 0,
        "skipped_same_timestamp": 0,
        "errors": [],
    }


def _online_read_result_payload() -> dict[str, Any]:
    return {
        "rows": [
            {
                "entity_key": {"customer_id": 123},
                "features": {
                    "transactions.avg_spend_30d": None,
                    "transactions.txn_count_30d": None,
                },
                "metadata": {
                    "transactions.avg_spend_30d": {
                        "found": True,
                        "event_timestamp": "2026-05-25T09:00:00Z",
                    },
                    "transactions.txn_count_30d": {
                        "found": False,
                        "event_timestamp": None,
                    },
                },
            }
        ]
    }


def test_write_online_features_posts_expected_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_online_write_result_payload())

    with _client_with_handler(handler) as client:
        client.write_online_features(
            rows=[
                {
                    "entity_key": {"customer_id": 123},
                    "feature_ref": "transactions.avg_spend_30d",
                    "value": 42.5,
                    "value_dtype": "float64",
                    "event_timestamp": "2026-05-25T09:00:00Z",
                }
            ],
            project="churn",
            feature_view="transactions",
            source_name="transactions",
            source_path="/data/transactions.parquet",
        )

    assert captured == {
        "method": "POST",
        "path": "/api/online/write",
        "body": {
            "project": "churn",
            "feature_view": "transactions",
            "source_name": "transactions",
            "source_path": "/data/transactions.parquet",
            "rows": [
                {
                    "entity_key": {"customer_id": 123},
                    "feature_ref": "transactions.avg_spend_30d",
                    "value": 42.5,
                    "value_dtype": "float64",
                    "event_timestamp": "2026-05-25T09:00:00Z",
                    "created_timestamp": None,
                    "source_name": None,
                    "source_path": None,
                    "write_id": None,
                }
            ],
        },
    }


def test_write_online_features_parses_count_result() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "requested": 2,
                "written": 1,
                "skipped_older": 1,
                "skipped_same_timestamp": 0,
                "errors": [],
            },
        )

    with _client_with_handler(handler) as client:
        result = client.write_online_features(
            rows=[
                {
                    "entity_key": {"customer_id": 123},
                    "feature_ref": "transactions.avg_spend_30d",
                    "value": 42.5,
                    "event_timestamp": "2026-05-25T09:00:00Z",
                }
            ]
        )

    assert isinstance(result, OnlineFeatureWriteResult)
    assert result.requested == 2
    assert result.written == 1
    assert result.skipped_older == 1


def test_get_online_features_posts_expected_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_online_read_result_payload())

    with _client_with_handler(handler) as client:
        client.get_online_features(
            entity_keys=[{"customer_id": 123}],
            feature_refs=["transactions.avg_spend_30d", "transactions.txn_count_30d"],
            project="churn",
            feature_view="transactions",
        )

    assert captured == {
        "method": "POST",
        "path": "/api/online/read",
        "body": {
            "project": "churn",
            "feature_view": "transactions",
            "entity_keys": [{"customer_id": 123}],
            "feature_refs": ["transactions.avg_spend_30d", "transactions.txn_count_30d"],
        },
    }


def test_get_online_features_parses_ordered_rows_and_metadata() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "rows": [
                    {
                        "entity_key": {"customer_id": 2},
                        "features": {"transactions.avg_spend_30d": 20.0},
                        "metadata": {
                            "transactions.avg_spend_30d": {
                                "found": True,
                                "event_timestamp": "2026-05-25T10:00:00Z",
                            }
                        },
                    },
                    {
                        "entity_key": {"customer_id": 1},
                        "features": {"transactions.avg_spend_30d": 10.0},
                        "metadata": {
                            "transactions.avg_spend_30d": {
                                "found": True,
                                "event_timestamp": "2026-05-25T09:00:00Z",
                            }
                        },
                    },
                ]
            },
        )

    with _client_with_handler(handler) as client:
        result = client.get_online_features(
            entity_keys=[{"customer_id": 2}, {"customer_id": 1}],
            feature_refs=["transactions.avg_spend_30d"],
        )

    assert isinstance(result, OnlineFeatureReadResult)
    assert [row.entity_key for row in result.rows] == [{"customer_id": 2}, {"customer_id": 1}]
    assert [row.features["transactions.avg_spend_30d"] for row in result.rows] == [20.0, 10.0]
    assert result.rows[0].metadata["transactions.avg_spend_30d"].found is True


def test_get_online_features_preserves_null_found_and_missing_metadata() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_online_read_result_payload())

    with _client_with_handler(handler) as client:
        result = client.get_online_features(
            entity_keys=[{"customer_id": 123}],
            feature_refs=["transactions.avg_spend_30d", "transactions.txn_count_30d"],
        )

    row = result.rows[0]
    assert row.features["transactions.avg_spend_30d"] is None
    assert row.metadata["transactions.avg_spend_30d"].found is True
    assert row.metadata["transactions.avg_spend_30d"].event_timestamp == datetime(
        2026, 5, 25, 9, 0, tzinfo=timezone.utc
    )
    assert row.features["transactions.txn_count_30d"] is None
    assert row.metadata["transactions.txn_count_30d"].found is False
    assert row.metadata["transactions.txn_count_30d"].event_timestamp is None


# --------------------------------------------------------------------------- #
# DataFrame paths — actual parquet reads                                       #
# --------------------------------------------------------------------------- #


def _write_temp_parquet(path: Any, columns: dict[str, list[Any]]) -> None:
    import polars as pl

    pl.DataFrame(columns).write_parquet(str(path))


def test_read_feature_returns_polars_column(
    tmp_path: Any, feature_payload: dict[str, Any], source_payload: dict[str, Any]
) -> None:
    parquet_path = tmp_path / "ub.parquet"
    _write_temp_parquet(parquet_path, {"user_id": [1, 2, 3], "session_count_30d": [10, 20, 30]})
    source_payload["path"] = str(parquet_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/features/by-name":
            return httpx.Response(200, json=feature_payload)
        if request.url.path == "/api/sources":
            return httpx.Response(200, json=[source_payload])
        return httpx.Response(404)

    with _client_with_handler(handler) as client:
        df = client.read_feature("user_behavior.session_count_30d")
    assert df.columns == ["session_count_30d"]
    assert df.height == 3


def test_get_group_to_polars_joins_on_user_id(
    tmp_path: Any, feature_payload: dict[str, Any], source_payload: dict[str, Any]
) -> None:
    """Two features in same parquet → join on ``user_id`` → 2-column frame."""
    parquet_path = tmp_path / "ub.parquet"
    _write_temp_parquet(
        parquet_path,
        {"user_id": [1, 2, 3], "session_count_30d": [10, 20, 30], "event_count_30d": [100, 200, 300]},
    )
    source_payload["path"] = str(parquet_path)

    feat2 = dict(feature_payload, id="f2", name="user_behavior.event_count_30d", column_name="event_count_30d")
    group = {
        "id": "g1",
        "name": "churn_v2",
        "description": "",
        "project": "",
        "owner": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "members": [feature_payload, feat2],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/groups/churn_v2":
            return httpx.Response(200, json=group)
        if request.url.path == "/api/sources":
            return httpx.Response(200, json=[source_payload])
        return httpx.Response(404)

    with _client_with_handler(handler) as client:
        detail = client.get_group("churn_v2")
        df = detail.to_polars(entity_key="user_id")
    assert set(df.columns) == {"user_id", "session_count_30d", "event_count_30d"}
    assert df.height == 3


def test_close_via_context_manager(feature_payload: dict[str, Any]) -> None:
    """Ensure the client closes the underlying httpx session on __exit__."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=feature_payload)

    with _client_with_handler(handler) as client:
        client.get_feature("x")
    # Calling again after close raises (httpx.Client)
    with pytest.raises(RuntimeError):
        client.get_feature("y")
