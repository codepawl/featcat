"""Configuration loading precedence and parsing."""

from __future__ import annotations


def test_env_overrides_project_yaml(tmp_path, monkeypatch):
    from featcat import config as cfg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_USER_PATH", tmp_path / "missing-user.yaml")
    (tmp_path / "featcat.yaml").write_text("llm_model: yaml-model\n")
    monkeypatch.setenv("FEATCAT_LLM_MODEL", "env-model")

    settings = cfg.load_settings()

    assert settings.llm_model == "env-model"
    assert cfg.get_setting_source("llm_model") == "env"


def test_cors_origins_accept_comma_separated_env(tmp_path, monkeypatch):
    from featcat import config as cfg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_USER_PATH", tmp_path / "missing-user.yaml")
    monkeypatch.setenv("FEATCAT_CORS_ORIGINS", "https://app.example, http://localhost:5173")

    settings = cfg.load_settings()

    assert settings.cors_origin_list() == ["https://app.example", "http://localhost:5173"]
    assert cfg.get_setting_source("cors_origins") == "env"


def test_db_settings_accept_matching_postgres_url(tmp_path, monkeypatch):
    from featcat import config as cfg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_USER_PATH", tmp_path / "missing-user.yaml")
    monkeypatch.setenv("FEATCAT_DB_BACKEND", "postgres")
    monkeypatch.setenv("FEATCAT_DB_URL", "postgresql+psycopg2://featcat:secret@postgres:5432/featcat")

    settings = cfg.load_settings()

    assert settings.db_backend == "postgres"
    assert settings.db_url == "postgresql+psycopg2://featcat:secret@postgres:5432/featcat"
    assert cfg.get_setting_source("db_backend") == "env"
    assert cfg.get_setting_source("db_url") == "env"


def test_db_settings_reject_mismatched_url_backend(tmp_path, monkeypatch):
    import pytest

    from featcat import config as cfg

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_USER_PATH", tmp_path / "missing-user.yaml")
    monkeypatch.setenv("FEATCAT_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEATCAT_DB_URL", "postgresql+psycopg2://featcat:secret@postgres:5432/featcat")

    with pytest.raises(ValueError, match="FEATCAT_DB_URL must match FEATCAT_DB_BACKEND"):
        cfg.load_settings()
