"""End-to-end CLI tests for `featcat setup` and `featcat quickstart`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def test_quickstart_writes_deploy_dir(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    runner = CliRunner()
    result = runner.invoke(app, ["quickstart", "--target", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "docker-compose.yml").exists()
    assert (target / ".env").exists()
    assert (target / "README.md").exists()
    assert (target / ".gitignore").exists()


def test_quickstart_refuses_non_empty_target(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    target.mkdir()
    (target / "x.txt").write_text("hi", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["quickstart", "--target", str(target)])
    assert result.exit_code != 0
    assert "not empty" in result.output.lower()


def test_setup_runs_with_default_inputs(tmp_path: Path) -> None:
    """Interactive wizard via stdin: feed defaults for every prompt."""
    target = tmp_path / "featcat-deploy"
    runner = CliRunner()
    # Four prompts: backend, port, data_dir, llm_model — accept defaults each.
    result = runner.invoke(app, ["setup", "--target", str(target)], input="\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert (target / "docker-compose.yml").exists()


def test_setup_choose_sqlite_omits_postgres(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    runner = CliRunner()
    # Pick sqlite, accept other defaults.
    result = runner.invoke(app, ["setup", "--target", str(target)], input="sqlite\n\n\n\n")
    assert result.exit_code == 0, result.output
    compose = (target / "docker-compose.yml").read_text(encoding="utf-8")
    assert "pgvector" not in compose
    assert "FEATCAT_DB_BACKEND=sqlite" in compose
