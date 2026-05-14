"""Tests for the setup template loader."""

from __future__ import annotations

import pytest

from featcat.setup.templates import (
    POSTGRES_COMPOSE_BLOCK,
    POSTGRES_DEPENDS_ON,
    POSTGRES_FEATCAT_ENV,
    render_template,
)


def test_render_docker_compose_postgres() -> None:
    out = render_template(
        "docker-compose.yml.tmpl",
        featcat_version="0.4.2",
        db_backend="postgres",
        server_port=8000,
        data_dir="./data",
        llm_model="gemma-4-E2B-it-Q4_K_M.gguf",
        compose_postgres_block=POSTGRES_COMPOSE_BLOCK,
        compose_postgres_env=POSTGRES_FEATCAT_ENV,
        compose_postgres_depends=POSTGRES_DEPENDS_ON,
    )
    assert "postgres:" in out
    assert "8000:8000" in out
    assert "gemma-4-E2B-it-Q4_K_M.gguf" in out


def test_render_docker_compose_sqlite_omits_postgres() -> None:
    out = render_template(
        "docker-compose.yml.tmpl",
        featcat_version="0.4.2",
        db_backend="sqlite",
        server_port=8000,
        data_dir="./data",
        llm_model="gemma-4-E2B-it-Q4_K_M.gguf",
        compose_postgres_block="",
        compose_postgres_env="",
        compose_postgres_depends="",
    )
    assert "pgvector" not in out
    assert "FEATCAT_DB_BACKEND=sqlite" in out


def test_render_dot_env_writes_credentials() -> None:
    out = render_template(
        "dot-env.tmpl",
        db_backend="postgres",
        db_password="secret123",
        server_port=8000,
        data_dir="./data",
        llm_model="gemma-4-E2B-it-Q4_K_M.gguf",
    )
    assert "POSTGRES_PASSWORD=secret123" in out


def test_render_template_errors_on_missing_placeholder() -> None:
    with pytest.raises(ValueError) as exc:
        render_template(
            "docker-compose.yml.tmpl",
            featcat_version="0.4.2",
            db_backend="sqlite",
            # Missing server_port / data_dir / llm_model / compose_* sections
        )
    assert "server_port" in str(exc.value) or "Template" in str(exc.value)
