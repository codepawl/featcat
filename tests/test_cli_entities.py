from __future__ import annotations

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import Entity, EntityRelationship
from featcat.cli import app

runner = CliRunner()


def test_entity_and_relationship_cli(tmp_path):
    db = LocalBackend(str(tmp_path / "cli-entities.db"))
    db.init_db()
    db.upsert_entity(Entity(name="customer", primary_keys=["customer_id"], join_keys=["customer_id"]))
    db.upsert_entity(Entity(name="contract", primary_keys=["contract_id"], join_keys=["contract_id", "customer_id"]))
    db.upsert_entity_relationship(
        EntityRelationship(
            name="customer_has_contracts",
            left_entity="customer",
            right_entity="contract",
            relation_type="one_to_many",
            join_keys=[{"left_key": "customer_id", "right_key": "customer_id"}],
        )
    )

    from featcat.cli import _get_db

    original = _get_db
    try:
        import featcat.cli as cli_module

        cli_module._get_db = lambda: db  # type: ignore[assignment]
        result = runner.invoke(app, ["entity", "list", "--json"])
        assert result.exit_code == 0
        assert '"name": "customer"' in result.output

        result = runner.invoke(app, ["relationship", "info", "customer_has_contracts"])
        assert result.exit_code == 0
        assert "customer_has_contracts" in result.output
    finally:
        import featcat.cli as cli_module

        cli_module._get_db = original  # type: ignore[assignment]
