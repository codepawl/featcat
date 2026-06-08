from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import yaml
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

runner = CliRunner()


def _write_parquet(path, data):
    table = pa.table(data)
    pq.write_table(table, path)


def test_feature_view_and_set_cli(tmp_path):
    db = LocalBackend(str(tmp_path / "feature-registry-cli.db"))
    db.init_db()
    source_path = tmp_path / "src.parquet"
    _write_parquet(source_path, {"bad_signal_days_7d": [1, 2, 3]})
    src = db.add_source(DataSource(name="src", path=str(source_path), format="parquet"))
    db.upsert_feature(
        Feature(
            name="src.bad_signal_days_7d",
            data_source_id=src.id,
            column_name="bad_signal_days_7d",
            entity_grain="customer_id",
        )
    )

    import featcat.cli as cli_module

    original = cli_module._get_db
    try:
        cli_module._get_db = lambda: db  # type: ignore[assignment]
        result = runner.invoke(app, ["feature-view", "info", "customer_network_view"])
        assert result.exit_code != 0

        result = runner.invoke(
            app,
            [
                "feature-view",
                "upsert",
                "customer_network_view",
                "--entity",
                "customer",
                "--source-name",
                "src",
                "--feature-name",
                "src.bad_signal_days_7d",
            ],
        )
        assert result.exit_code == 0

        result = runner.invoke(
            app,
            [
                "feature-set",
                "upsert",
                "churn_features_v1",
                "--target-entity",
                "customer",
                "--feature-name",
                "src.bad_signal_days_7d",
            ],
        )
        assert result.exit_code == 0
    finally:
        cli_module._get_db = original  # type: ignore[assignment]


def test_apply_cli_registers_registry_config(tmp_path):
    db = LocalBackend(str(tmp_path / "apply.db"))
    db.init_db()

    source_path = tmp_path / "src.parquet"
    _write_parquet(source_path, {"bad_signal_days_7d": [1, 2, 3]})

    config_path = tmp_path / "featcat.yaml"
    config = {
        "sources": [
            {
                "name": "src",
                "path": str(source_path),
                "format": "parquet",
                "entity_key": "customer_id",
            }
        ],
        "entities": [
            {"name": "customer", "primary_keys": ["customer_id"], "join_keys": ["customer_id"]},
            {"name": "device", "primary_keys": ["device_id"], "join_keys": ["device_id", "customer_id"]},
        ],
        "relationships": [
            {
                "name": "customer_has_devices",
                "left_entity": "customer",
                "right_entity": "device",
                "relation_type": "one_to_many",
                "join_keys": [{"left_key": "customer_id", "right_key": "customer_id"}],
            }
        ],
        "features": [
            {
                "source_name": "src",
                "column_name": "bad_signal_days_7d",
                "entity_grain": "customer_id",
                "leakage_risk": "low",
            }
        ],
        "feature_views": [
            {
                "name": "customer_network_view",
                "entity": "customer",
                "source_name": "src",
                "feature_names": ["src.bad_signal_days_7d"],
            }
        ],
        "business_metrics": [
            {
                "name": "network.bad_signal_days_7d",
                "business_metric_name": "bad_signal_days_7d",
                "metric_domain": "network_quality",
                "lifecycle_stage": "consume",
                "metric_level": "customer",
                "entity_grain": "customer_id",
                "mapped_features": ["src.bad_signal_days_7d"],
            }
        ],
        "feature_sets": [
            {
                "name": "churn.customer_set",
                "target_entity": "customer",
                "feature_names": ["src.bad_signal_days_7d"],
            }
        ],
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    import featcat.cli as cli_module

    original = cli_module._get_db
    try:
        cli_module._get_db = lambda: db  # type: ignore[assignment]
        result = runner.invoke(app, ["apply", str(config_path)])
        assert result.exit_code == 0
        assert db.get_source_by_name("src") is not None
        assert db.get_entity_by_name("customer") is not None
        assert db.get_entity_relationship_by_name("customer_has_devices") is not None
        assert db.get_feature_by_name("src.bad_signal_days_7d") is not None
        assert db.get_feature_view_by_name("customer_network_view") is not None
        assert db.get_business_metric_by_name("network.bad_signal_days_7d") is not None
        assert db.get_feature_set_by_name("churn.customer_set") is not None
    finally:
        cli_module._get_db = original  # type: ignore[assignment]
