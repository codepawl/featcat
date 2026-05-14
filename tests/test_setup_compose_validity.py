"""Validate the generated compose file with `docker compose config`.

Skipped when docker is not on PATH (e.g. on a CI box without the daemon).
The check shells out to docker compose with --quiet so the test only fails
if compose parses the file as invalid.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from featcat.setup.quickstart import run_quickstart

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not available")
def test_quickstart_compose_passes_docker_compose_config(tmp_path: Path) -> None:
    target = tmp_path / "featcat-deploy"
    run_quickstart(target_dir=target)
    result = subprocess.run(
        ["docker", "compose", "config", "--quiet"],
        cwd=target,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
