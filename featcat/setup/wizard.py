"""Interactive setup wizard.

Builds a ``WizardAnswers`` from rich prompts and writes the deploy
directory. The wizard is intentionally short — it asks only what the
quickstart can't guess and lets the operator accept defaults by pressing
Enter.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from .. import __version__ as _featcat_version
from .templates import (
    POSTGRES_COMPOSE_BLOCK,
    POSTGRES_DEPENDS_ON,
    POSTGRES_FEATCAT_ENV,
    render_template,
)

_console = Console()


@dataclass(frozen=True)
class WizardAnswers:
    db_backend: Literal["sqlite", "postgres"]
    server_port: int
    data_dir: str
    llm_model: str
    target_dir: Path
    db_password: str = ""


def run_wizard(*, target_dir: Path | None = None, console: Console | None = None) -> WizardAnswers:
    """Prompt the operator for deployment choices and write the deploy dir."""
    c = console or _console
    target = target_dir or Path("./featcat-deploy")

    c.print("[bold]featcat setup[/bold] — generate a deployment directory")
    db = Prompt.ask("Database backend", choices=["postgres", "sqlite"], default="postgres")
    port = IntPrompt.ask("Server port", default=8000)
    data_dir = Prompt.ask("Host data directory (mounted at /sources)", default="./data")
    llm_model = Prompt.ask("LLM model filename", default="gemma-4-E2B-it-Q4_K_M.gguf")

    answers = WizardAnswers(
        db_backend=db,  # type: ignore[arg-type]
        server_port=port,
        data_dir=data_dir,
        llm_model=llm_model,
        target_dir=target,
        db_password=secrets.token_urlsafe(24) if db == "postgres" else "",
    )
    write_deploy_dir(answers, console=c)
    return answers


def write_deploy_dir(answers: WizardAnswers, *, console: Console | None = None) -> None:
    """Render every template and write the deploy directory.

    Raises ``FileExistsError`` if ``answers.target_dir`` exists and is
    non-empty so we don't clobber an operator's work.
    """
    target = answers.target_dir
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Target directory {target} is not empty.")
    target.mkdir(parents=True, exist_ok=True)

    is_postgres = answers.db_backend == "postgres"
    compose = render_template(
        "docker-compose.yml.tmpl",
        featcat_version=_featcat_version,
        db_backend=answers.db_backend,
        server_port=answers.server_port,
        data_dir=answers.data_dir,
        llm_model=answers.llm_model,
        compose_postgres_block=POSTGRES_COMPOSE_BLOCK if is_postgres else "",
        compose_postgres_env=POSTGRES_FEATCAT_ENV if is_postgres else "",
        compose_postgres_depends=POSTGRES_DEPENDS_ON if is_postgres else "",
    )
    (target / "docker-compose.yml").write_text(compose, encoding="utf-8")

    env = render_template(
        "dot-env.tmpl",
        db_backend=answers.db_backend,
        db_password=answers.db_password or "_unused_",
        server_port=answers.server_port,
        data_dir=answers.data_dir,
        llm_model=answers.llm_model,
    )
    (target / ".env").write_text(env, encoding="utf-8")

    (target / ".gitignore").write_text(render_template("dot-gitignore.tmpl"), encoding="utf-8")
    (target / "README.md").write_text(
        render_template(
            "README.md.tmpl",
            db_backend=answers.db_backend,
            server_port=answers.server_port,
            data_dir=answers.data_dir,
        ),
        encoding="utf-8",
    )

    c = console or _console
    c.print(f"[green]Wrote deployment directory:[/green] {target}")
