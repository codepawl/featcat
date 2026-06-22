"""Business metric route tests without FastAPI TestClient."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import BusinessMetric, DataSource, Feature
from featcat.server.app import build_app
from featcat.server.routes.business_metrics import (
    BusinessMetricCsvImportRequest,
    BusinessMetricUpsertRequest,
    get_business_metric_by_name,
    import_business_metrics_csv,
    list_business_metrics,
    upsert_business_metric,
)

if TYPE_CHECKING:
    from pathlib import Path


def _backend(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    return db


def _seed_metric(db: LocalBackend, tmp_path: Path) -> Feature:
    source = DataSource(name="network_quality_customer_7d", path=str(tmp_path / "network.parquet"))
    db.add_source(source)
    feature = Feature(
        name="network_quality_customer_7d.bad_signal_days_7d",
        data_source_id=source.id,
        column_name="bad_signal_days_7d",
        dtype="int64",
    )
    db.upsert_feature(feature)
    return feature


def test_business_metric_routes_are_registered_without_testclient() -> None:
    routes = {
        (route.path, tuple(sorted(route.methods or []))) for route in build_app().routes if isinstance(route, APIRoute)
    }
    assert ("/api/business-metrics", ("GET",)) in routes
    assert ("/api/business-metrics", ("POST",)) in routes
    assert ("/api/business-metrics/by-name", ("GET",)) in routes
    assert ("/api/business-metrics/import-csv", ("POST",)) in routes


def test_business_metric_route_crud_and_filters(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        feature = _seed_metric(db, tmp_path)
        request = BusinessMetricUpsertRequest(
            name="network_quality.bad_signal_days_7d",
            business_metric_name="bad_signal_days_7d",
            business_definition="So ngay tin hieu kem trong 7 ngay gan nhat",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_group="signal",
            metric_level="customer",
            entity_grain="customer_id",
            mapped_features=[feature.name],
            owner="network-data",
            allowed_use_cases=["churn"],
        )
        created = upsert_business_metric(request, db=db)
        filtered = list_business_metrics(
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_level="customer",
            owner="network-data",
            search="bad_signal",
            db=db,
        )
        looked_up = get_business_metric_by_name(request.name, db=db)
    finally:
        db.close()

    assert created.name == request.name
    assert created.mapped_features == [feature.name]
    assert filtered and filtered[0].name == request.name
    assert looked_up.metric_domain == "network_quality"
    assert looked_up.allowed_use_cases == ["churn"]


def test_business_metric_route_searches_objective_text(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        feature = _seed_metric(db, tmp_path)
        db.upsert_business_metric(
            BusinessMetric(
                name="network_quality.downtime_minutes_7d",
                business_metric_name="downtime_minutes_7d",
                business_definition="Downtime minutes for contract and customer experience",
                metric_domain="network_quality",
                lifecycle_stage="consume",
                metric_group="availability",
                metric_level="mixed",
                entity_grain="device_id",
                aggregation_rule="sum by contract_id then customer_id",
                mapped_features=[feature.name],
            )
        )
        matches = list_business_metrics(business_objective="downtime", db=db)
    finally:
        db.close()

    assert [metric.name for metric in matches] == ["network_quality.downtime_minutes_7d"]


def test_business_metric_import_csv_dry_run_and_commit(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    csv_text = (
        "\ufeffStage,Domain,Metric Number,Metric Name,Definition,Data Sources,Status,View\n"
        'Consume,Product,ME-C-D-01,product-net-device-clients,"Line one\nLine two",ACS Server & TR-069,Done,Device\n'
        "Recommend,Customer,ME-M-CT-09,LowCSAT,Số lượng CSAT 1;2,Survey System,Processing,Per-Contract\n"
    )
    try:
        preview = import_business_metrics_csv(
            BusinessMetricCsvImportRequest(csv_text=csv_text, namespace="cx360", owner="cx-team", dry_run=True),
            db=db,
        )
        assert preview.total == 2
        assert preview.created == 2
        assert preview.updated == 0
        assert preview.skipped == 0
        assert db.list_business_metrics() == []

        result = import_business_metrics_csv(
            BusinessMetricCsvImportRequest(csv_text=csv_text, namespace="cx360", owner="cx-team"),
            db=db,
        )
        metrics = db.list_business_metrics(owner="cx-team")
    finally:
        db.close()

    assert result.created == 2
    assert {metric.business_metric_name for metric in metrics} == {"LowCSAT", "product-net-device-clients"}
    device_metric = next(metric for metric in metrics if metric.business_metric_name == "product-net-device-clients")
    assert device_metric.metric_domain == "product"
    assert device_metric.lifecycle_stage == "consume"
    assert device_metric.metric_level == "device"
    assert device_metric.business_definition == "Line one\nLine two"
    assert device_metric.source_systems == ["ACS Server & TR-069"]
    assert device_metric.implementation_status == "done"
    assert device_metric.lifecycle_status == "validated"
    assert device_metric.mapped_features == []


def test_business_metric_import_csv_rejects_missing_required_headers(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        with pytest.raises(HTTPException) as exc_info:
            import_business_metrics_csv(
                BusinessMetricCsvImportRequest(csv_text="Name,Definition\nBad row,Missing taxonomy\n"),
                db=db,
            )
    finally:
        db.close()

    assert exc_info.value.status_code == 400
    assert "CSV missing required columns" in str(exc_info.value.detail)
