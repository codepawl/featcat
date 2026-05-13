"""Tests for FeatCatClient.

Uses ``httpx.MockTransport`` to inject server responses without a live server.
A dispatcher inspects ``request.url.path`` + method and returns the right
``httpx.Response``. Test scope mirrors the public API surface plus the retry
and error-wrapping invariants.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from featcat_client import (
    ConnectionError,
    FeatCatClient,
    Feature,
    FeatureGroupDetail,
    FeatureNotFound,
    GroupNotFound,
    ServerError,
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
