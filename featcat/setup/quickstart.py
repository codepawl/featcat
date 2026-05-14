"""Non-interactive quickstart — defaults only, no prompts."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from .wizard import WizardAnswers, write_deploy_dir

if TYPE_CHECKING:
    from rich.console import Console

_DEFAULT_BACKEND: Literal["sqlite", "postgres"] = "postgres"
_DEFAULT_PORT = 8000
_DEFAULT_DATA_DIR = "./data"
_DEFAULT_LLM_MODEL = "gemma-4-E2B-it-Q4_K_M.gguf"


def run_quickstart(*, target_dir: Path | None = None, console: Console | None = None) -> WizardAnswers:
    target = target_dir or Path("./featcat-deploy")
    answers = WizardAnswers(
        db_backend=_DEFAULT_BACKEND,
        server_port=_DEFAULT_PORT,
        data_dir=_DEFAULT_DATA_DIR,
        llm_model=_DEFAULT_LLM_MODEL,
        target_dir=target,
        db_password=secrets.token_urlsafe(24),
    )
    write_deploy_dir(answers, console=console)
    return answers
