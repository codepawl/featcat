"""Probe the local environment for the setup wizard.

Functions never raise — they return a best-effort ``EnvReport``. Anything
that can be slow (docker info) is timeout-bounded so the wizard stays
snappy on machines without Docker.
"""

from __future__ import annotations

import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class EnvReport:
    python_version: str
    platform_system: str
    docker_path: str | None
    docker_available: bool
    git_path: str | None


def detect_environment() -> EnvReport:
    """Best-effort environment probe; never raises."""
    docker_path = shutil.which("docker")
    docker_ok = False
    if docker_path:
        try:
            result = subprocess.run(
                [docker_path, "info"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            docker_ok = result.returncode == 0
        except Exception:
            docker_ok = False
    return EnvReport(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform_system=platform.system(),
        docker_path=docker_path,
        docker_available=docker_ok,
        git_path=shutil.which("git"),
    )


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if ``port`` is not currently bound on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False
