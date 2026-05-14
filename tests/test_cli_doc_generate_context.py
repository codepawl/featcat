"""Verify `featcat doc generate --context X` reaches AutodocPlugin.execute."""

from __future__ import annotations

from unittest.mock import MagicMock

from typer.testing import CliRunner

from featcat.cli import app
from featcat.plugins.base import PluginResult


def test_doc_generate_passes_context_to_plugin(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePlugin:
        def execute(self, db: object, llm: object, **kwargs: object) -> PluginResult:
            captured.update(kwargs)
            return PluginResult(status="success", data={"documented": 1}, errors=[])

    monkeypatch.setattr("featcat.cli._get_db", lambda: MagicMock())
    monkeypatch.setattr("featcat.cli._get_llm", lambda use_cache=True: MagicMock())
    monkeypatch.setattr("featcat.plugins.autodoc.AutodocPlugin", FakePlugin)

    runner = CliRunner()
    result = runner.invoke(
        app, ["doc", "generate", "src.x", "--context", "DS team focus on churn"]
    )
    assert result.exit_code == 0, result.output
    assert captured.get("context") == "DS team focus on churn"


def test_doc_generate_without_context_passes_none(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakePlugin:
        def execute(self, db: object, llm: object, **kwargs: object) -> PluginResult:
            captured.update(kwargs)
            return PluginResult(status="success", data={"documented": 1}, errors=[])

    monkeypatch.setattr("featcat.cli._get_db", lambda: MagicMock())
    monkeypatch.setattr("featcat.cli._get_llm", lambda use_cache=True: MagicMock())
    monkeypatch.setattr("featcat.plugins.autodoc.AutodocPlugin", FakePlugin)

    runner = CliRunner()
    result = runner.invoke(app, ["doc", "generate", "src.x"])
    assert result.exit_code == 0
    assert captured.get("context") is None
