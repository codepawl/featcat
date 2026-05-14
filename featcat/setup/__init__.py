"""Setup wizard and quickstart helpers.

The wizard walks operators through deployment choices (db backend, ports,
data dir, LLM model) and writes a complete ``featcat-deploy/`` directory.
Quickstart is the non-interactive variant — it picks sensible defaults
and writes the same files in one shot.

Templates live in ``featcat/templates/setup/`` and use plain
``str.format`` substitution; no jinja2 dependency is added.
"""

from __future__ import annotations

from .detect import EnvReport, detect_environment, is_port_free
from .quickstart import run_quickstart
from .templates import render_template
from .wizard import WizardAnswers, run_wizard, write_deploy_dir

__all__ = [
    "EnvReport",
    "WizardAnswers",
    "detect_environment",
    "is_port_free",
    "render_template",
    "run_quickstart",
    "run_wizard",
    "write_deploy_dir",
]
