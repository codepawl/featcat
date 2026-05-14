"""Tests for the setup wizard and quickstart flows."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from featcat.setup.quickstart import run_quickstart
from featcat.setup.wizard import WizardAnswers, write_deploy_dir

if TYPE_CHECKING:
    from pathlib import Path


def test_write_deploy_dir_creates_all_files(tmp_path: Path) -> None:
    answers = WizardAnswers(
        db_backend="postgres",
        server_port=8000,
        data_dir="./data",
        llm_model="gemma-4-E2B-it-Q4_K_M.gguf",
        target_dir=tmp_path / "featcat-deploy",
        db_password="test-secret",
    )
    write_deploy_dir(answers)
    target = tmp_path / "featcat-deploy"
    assert (target / "docker-compose.yml").exists()
    assert (target / ".env").exists()
    assert (target / ".gitignore").exists()
    assert (target / "README.md").exists()


def test_write_deploy_dir_refuses_non_empty_target(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    target.mkdir()
    (target / "existing.txt").write_text("hi", encoding="utf-8")
    answers = WizardAnswers(
        db_backend="sqlite",
        server_port=8000,
        data_dir="./data",
        llm_model="gemma-4-E2B-it-Q4_K_M.gguf",
        target_dir=target,
    )
    with pytest.raises(FileExistsError):
        write_deploy_dir(answers)


def test_run_quickstart_default_writes_postgres_deploy(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    answers = run_quickstart(target_dir=target)
    assert answers.db_backend == "postgres"
    assert (target / "docker-compose.yml").exists()
    compose = (target / "docker-compose.yml").read_text(encoding="utf-8")
    assert "pgvector" in compose


def test_quickstart_generates_unique_db_password(tmp_path: Path) -> None:
    a = run_quickstart(target_dir=tmp_path / "a")
    b = run_quickstart(target_dir=tmp_path / "b")
    assert a.db_password != b.db_password
    assert len(a.db_password) >= 20


def test_quickstart_env_holds_password(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    answers = run_quickstart(target_dir=target)
    env = (target / ".env").read_text(encoding="utf-8")
    assert f"POSTGRES_PASSWORD={answers.db_password}" in env
