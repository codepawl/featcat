from __future__ import annotations

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import (
    BusinessMetric,
    DataSource,
    Entity,
    EntityRelationship,
    Feature,
    FeatureSet,
    FeatureView,
)
from featcat.sdk import FeatcatSDK

if TYPE_CHECKING:
    from pathlib import Path


def _write_parquet(path: Path, data: dict[str, list[object]]) -> None:
    table = pa.table(data)
    pq.write_table(table, path)


def test_sdk_registers_registry_objects(tmp_path: Path, monkeypatch) -> None:
    db = LocalBackend(str(tmp_path / "sdk.db"))
    db.init_db()
    monkeypatch.setattr("featcat.sdk.get_backend", lambda: db)

    source_path = tmp_path / "src.parquet"
    _write_parquet(source_path, {"bad_signal_days_7d": [1, 2, 3]})
    source = db.add_source(
        DataSource(
            name="src",
            path=str(source_path),
            format="parquet",
            entity_key="customer_id",
            event_timestamp_column="event_ts",
            created_timestamp_column="created_ts",
        )
    )

    with FeatcatSDK() as sdk:
        entity = sdk.register_entity(
            Entity(name="customer", primary_keys=["customer_id"], join_keys=["customer_id"], lifecycle_status="draft")
        )
        contract = sdk.register_entity(
            Entity(name="contract", primary_keys=["contract_id"], join_keys=["contract_id", "customer_id"])
        )
        relationship = sdk.register_relationship(
            EntityRelationship(
                name="customer_has_contracts",
                left_entity="customer",
                right_entity="contract",
                relation_type="one_to_many",
                join_keys=[{"left_key": "customer_id", "right_key": "customer_id"}],
            )
        )
        feature = sdk.register_feature(
            Feature(
                name="src.bad_signal_days_7d",
                data_source_id=source.id,
                column_name="bad_signal_days_7d",
                entity_grain="device_id",
                leakage_risk="low",
            )
        )
        view = sdk.register_feature_view(
            FeatureView(
                name="network.bad_signal_view",
                entity="customer",
                source_name="src",
                source_entity="device",
                relationship="customer_has_contracts",
                aggregation="sum by customer_id",
                feature_names=[feature.name],
            )
        )
        metric = sdk.register_business_metric(
            BusinessMetric(
                name="network.bad_signal_days_7d",
                business_metric_name="Bad signal days 7d",
                metric_domain="network_quality",
                lifecycle_stage="consume",
                metric_level="customer",
                entity_grain="customer_id",
                aggregation_rule="sum(device bad signal days) by customer_id",
                mapped_features=[feature.name],
            )
        )
        feature_set = sdk.register_feature_set(
            FeatureSet(
                name="churn.customer_set",
                target_entity="customer",
                feature_names=[feature.name],
                rollup_rules={feature.name: "sum(device bad signal days) by customer_id"},
            )
        )

        assert sdk.get_entity("customer") == entity
        assert sdk.get_entity("contract") == contract
        assert sdk.get_relationship("customer_has_contracts") == relationship
        assert sdk.get_feature_view("network.bad_signal_view") == view
        assert sdk.get_business_metric("network.bad_signal_days_7d") == metric
        assert sdk.get_feature_set("churn.customer_set") == feature_set
        assert sdk.list_entities()
        assert sdk.list_relationships()
        assert sdk.list_feature_views()
        assert sdk.list_business_metrics()
        assert sdk.list_feature_sets()
