"""Application configuration via Pydantic BaseSettings with YAML file support."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, model_validator
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
    llm_backend: str = "llamacpp"
    llm_model: str = "gemma-4-E2B-it"
    llamacpp_url: str = "http://localhost:8080"
    llm_timeout: int = 300  # seconds
    llm_max_retries: int = 3

    # Catalog
    catalog_db_path: str = "catalog.db"
    max_context_features: int = 100

    # S3 / MinIO
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_session_token: str | None = None  # For STS / role-assume credentials
    s3_region: str = "us-east-1"
    s3_force_path_style: bool = True
    s3_connect_timeout_ms: int = 10_000  # Passed to PyArrow S3FileSystem (converted to seconds)
    s3_request_timeout_ms: int = 60_000

    # Online store backend: "sql" (default, uses DB table) or "redis" (Redis hash-based store).
    online_store_backend: str = "sql"
    redis_url: str = "redis://localhost:6379/0"

    # Server mode
    server_url: str | None = None  # If set, use RemoteBackend instead of local SQLite
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    server_auth_token: str | None = None
    cors_origins: str | list[str] = "*"

    # Internal auth for the web UI / API. When enabled, requests must carry
    # a trusted identity header from the internal SSO proxy or the shared
    # service bearer token. Roles are derived from the configured email/group
    # allowlists.
    auth_required: bool = False
    auth_identity_headers: list[str] = [
        "X-Auth-Request-Email",
        "X-Forwarded-Email",
        "Cf-Access-Authenticated-User-Email",
        "X-User-Email",
    ]
    auth_group_headers: list[str] = [
        "X-Auth-Request-Groups",
        "X-Forwarded-Groups",
        "Cf-Access-Groups",
    ]
    auth_admin_users: list[str] = []
    auth_editor_users: list[str] = []
    auth_admin_groups: list[str] = []
    auth_editor_groups: list[str] = []
    auth_allowed_email_domains: list[str] = ["fpt.com"]

    # Monitoring
    monitor_interval_minutes: int = 10
    scheduler_enabled: bool = True

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

    # Tasks backend: "apscheduler" (default, in-process) or "celery" (out-of-process via Redis broker).
    # When "celery", the FeatcatScheduler still drives cron triggers but dispatches the actual job
    # work to Celery workers via .delay(). The [tasks] extra must be installed for "celery" mode.
    tasks_backend: str = "apscheduler"

    @model_validator(mode="before")
    @classmethod
    def _normalize_cors_origins(cls, data: Any) -> Any:
        """Accept FEATCAT_CORS_ORIGINS as JSON list or comma-separated text."""
        if not isinstance(data, dict):
            return data
        raw = data.get("cors_origins")
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            data["cors_origins"] = parts or ["*"]
        return data

    @model_validator(mode="after")
    def _validate_s3_paired_keys(self) -> Settings:
        """Reject partial S3 credential config.

        Historical bug: ``_get_s3_filesystem`` used ``if access and secret:``
        which silently dropped both keys when only one was set, falling back
        to PyArrow's default chain — surprising and hard to debug. Failing at
        config load instead gives the operator the error before any S3 call.
        Both keys must be set together, or both unset (then the default
        credential chain handles things).
        """
        if self.s3_access_key and self.s3_access_key_id and self.s3_access_key != self.s3_access_key_id:
            raise ValueError("Set only one of FEATCAT_S3_ACCESS_KEY and FEATCAT_S3_ACCESS_KEY_ID")
        if self.s3_secret_key and self.s3_secret_access_key and self.s3_secret_key != self.s3_secret_access_key:
            raise ValueError("Set only one of FEATCAT_S3_SECRET_KEY and FEATCAT_S3_SECRET_ACCESS_KEY")

        access_key = self.s3_access_key_id or self.s3_access_key
        secret_key = self.s3_secret_access_key or self.s3_secret_key
        has_access = bool(access_key)
        has_secret = bool(secret_key)
        if has_access != has_secret:
            raise ValueError(
                "FEATCAT_S3_ACCESS_KEY_ID and FEATCAT_S3_SECRET_ACCESS_KEY must be set together or both unset "
                f"(currently: access_key={'set' if has_access else 'unset'}, "
                f"secret_key={'set' if has_secret else 'unset'})"
            )
        return self

    def cors_origin_list(self) -> list[str]:
        """Return configured CORS origins as a list for Starlette middleware."""
        raw = self.cors_origins
        if isinstance(raw, str):
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            return parts or ["*"]
        return raw or ["*"]


# Keep a record of which keys came from which source for `config show`
_setting_sources: dict[str, str] = {}


def load_settings(overrides: dict[str, Any] | None = None) -> Settings:
    """Load settings with priority: overrides > env vars > project YAML > user YAML > defaults."""
    all_keys = set(Settings.model_fields.keys())

    # Layer 1: user config
    user_config = _load_yaml(CONFIG_USER_PATH)
    # Layer 2: project config
    project_config = _load_yaml(CONFIG_PROJECT_PATH)
    # Layer 3: env config, parsed by pydantic-settings so types match Settings.
    env_settings = Settings()
    env_keys = {key for key in all_keys if f"FEATCAT_{key.upper()}" in os.environ}
    env_config = {key: getattr(env_settings, key) for key in env_keys}

    # Merge: start with user, then project, env, and explicit overrides.
    merged: dict[str, Any] = {}
    merged.update(user_config)
    merged.update(project_config)
    merged.update(env_config)

    if overrides:
        merged.update(overrides)

    # Track sources for config show
    _setting_sources.clear()

    for key in all_keys:
        if overrides and key in overrides:
            _setting_sources[key] = "override"
        elif key in env_config:
            _setting_sources[key] = "env"
        elif key in project_config:
            _setting_sources[key] = "project"
        elif key in user_config:
            _setting_sources[key] = "user"
        else:
            _setting_sources[key] = "default"

    return Settings(_env_prefix="__FEATCAT_DISABLED__", **{k: v for k, v in merged.items() if k in all_keys})


def get_setting_source(key: str) -> str:
    """Return the source of a setting value: 'default', 'user', 'project', 'env', or 'override'."""
    return _setting_sources.get(key, "default")


def get_all_setting_sources() -> dict[str, str]:
    """Return source map for all settings."""
    return dict(_setting_sources)
