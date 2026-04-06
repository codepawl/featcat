"""Application configuration via Pydantic BaseSettings with YAML file support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings

CONFIG_USER_DIR = Path.home() / ".config" / "featcat"
CONFIG_USER_PATH = CONFIG_USER_DIR / "config.yaml"
CONFIG_PROJECT_PATH = Path("featcat.yaml")


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML config file, returning empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    """Write a dict to a YAML config file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=True)


class TaskLLMConfig(BaseModel):
    """Per-task LLM configuration overrides."""

    model: str | None = None  # None = use default llm_model
    temperature: float | None = None  # None = use plugin default


class Settings(BaseSettings):
    """featcat configuration, loaded from env vars (FEATCAT_*) or featcat.yaml."""

    model_config = {"env_prefix": "FEATCAT_"}

    # LLM
    llm_backend: str = "ollama"  # "ollama" | "llamacpp"
    llm_model: str = "qwen2.5:7b"
    ollama_url: str = "http://localhost:11434"
    llamacpp_url: str = "http://localhost:8080"
    llm_timeout: int = 120  # seconds
    llm_max_retries: int = 3

    # Catalog
    catalog_db_path: str = "catalog.db"
    max_context_features: int = 100

    # S3 / MinIO
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "us-east-1"

    # Server mode
    server_url: str | None = None  # If set, use RemoteBackend instead of local SQLite
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_auth_token: str | None = None

    # Monitoring
    monitor_interval_minutes: int = 10

    # Defaults for add command
    default_owner: str = ""
    auto_doc: bool = True

    # Language
    language: str = "en"  # "en" | "vi"

    # Per-task LLM overrides (model, temperature)
    task_autodoc: TaskLLMConfig = TaskLLMConfig(temperature=0.1)
    task_discovery: TaskLLMConfig = TaskLLMConfig(temperature=0.3)
    task_monitoring: TaskLLMConfig = TaskLLMConfig(temperature=0.05)
    task_nl_query: TaskLLMConfig = TaskLLMConfig(temperature=0.2)

    # Monitoring thresholds
    monitoring_threshold_warning: float = 0.1
    monitoring_threshold_critical: float = 0.25

    # Job scheduler defaults (used to seed job_schedules on first run)
    job_monitor_check_cron: str = "0 */6 * * *"
    job_doc_generate_cron: str = "0 2 * * *"
    job_source_scan_cron: str = "0 1 * * *"
    job_baseline_refresh_cron: str = "0 3 * * 0"


# Keep a record of which keys came from which source for `config show`
_setting_sources: dict[str, str] = {}


def load_settings(overrides: dict[str, Any] | None = None) -> Settings:
    """Load settings with priority: overrides > env vars > project YAML > user YAML > defaults.

    Env vars are handled automatically by pydantic-settings on top of the init kwargs.
    """
    defaults = Settings()
    default_dict = defaults.model_dump()

    # Layer 1: user config
    user_config = _load_yaml(CONFIG_USER_PATH)
    # Layer 2: project config
    project_config = _load_yaml(CONFIG_PROJECT_PATH)

    # Merge: start with user, then project on top
    merged: dict[str, Any] = {}
    merged.update(user_config)
    merged.update(project_config)

    if overrides:
        merged.update(overrides)

    # Track sources for config show
    _setting_sources.clear()
    all_keys = set(default_dict.keys())

    for key in all_keys:
        if overrides and key in overrides:
            _setting_sources[key] = "override"
        elif key in project_config:
            _setting_sources[key] = "project"
        elif key in user_config:
            _setting_sources[key] = "user"
        else:
            _setting_sources[key] = "default"

    # Build settings: pass merged YAML as init kwargs, env vars override via pydantic-settings
    settings = Settings(**{k: v for k, v in merged.items() if k in all_keys})

    # Re-check: if env var is set and differs from YAML value, mark as "env"
    env_settings = Settings()  # Pure env-only load
    for key in all_keys:
        env_val = getattr(env_settings, key)
        final_val = getattr(settings, key)
        yaml_val = merged.get(key)
        from_env = (
            yaml_val is not None and env_val != default_dict[key] and final_val == env_val and env_val != yaml_val
        ) or (yaml_val is None and env_val != default_dict[key])
        if from_env:
            _setting_sources[key] = "env"

    return settings


def get_setting_source(key: str) -> str:
    """Return the source of a setting value: 'default', 'user', 'project', 'env', or 'override'."""
    return _setting_sources.get(key, "default")


def get_all_setting_sources() -> dict[str, str]:
    """Return source map for all settings."""
    return dict(_setting_sources)
