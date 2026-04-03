"""Application configuration via Pydantic BaseSettings."""

from __future__ import annotations

from pydantic_settings import BaseSettings


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

    # Monitoring
    monitor_interval_minutes: int = 10


def load_settings() -> Settings:
    """Load settings from environment variables."""
    return Settings()
