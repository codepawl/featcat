"""Deploy checks for ``featcat doctor deploy``.

These checks probe host-level state: Git working tree, Docker daemon, the
docker-compose file. They emit ``SKIP`` (never ``FAIL``) when context isn't
available — featcat ships as a pip-installable package that runs in many
contexts where neither Git nor Docker apply.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .models import CheckResult, CheckStatus
from .runner import register

if TYPE_CHECKING:
    from featcat.config import Settings


_GIT_TIMEOUT_S = 1.0
_DOCKER_TIMEOUT_S = 1.5
_COMPOSE_CANDIDATES = (
    Path("deploy/docker-compose.yml"),
    Path("docker-compose.yml"),
)


def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    """Run ``cmd``, capture combined output, return (returncode, output)."""
    proc = subprocess.run(  # noqa: S603 — args are constructed from constants, never user input
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr).strip()


@register("deploy")
def deploy_git(_settings: Settings) -> CheckResult:
    """Working-tree health: clean? on a sensible branch? ahead/behind upstream?"""
    if shutil.which("git") is None:
        return CheckResult(name="deploy_git", status=CheckStatus.SKIP, detail="git not in PATH")
    if not Path(".git").exists():
        return CheckResult(
            name="deploy_git",
            status=CheckStatus.SKIP,
            detail="no working tree (running from installed package)",
        )
    try:
        rc, out = _run(["git", "status", "--porcelain=v1", "-b"], _GIT_TIMEOUT_S)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return CheckResult(name="deploy_git", status=CheckStatus.SKIP, detail=f"git probe failed: {exc}")
    if rc != 0:
        return CheckResult(name="deploy_git", status=CheckStatus.FAIL, detail=f"git status rc={rc}: {out}")
    lines = out.splitlines()
    branch_line = lines[0] if lines else ""
    dirty = any(not line.startswith("##") for line in lines)
    detail = branch_line.lstrip("# ").strip()
    if dirty:
        return CheckResult(
            name="deploy_git",
            status=CheckStatus.WARN,
            detail=f"{detail} (uncommitted changes)",
            resolution="Commit or stash before deploying",
        )
    return CheckResult(name="deploy_git", status=CheckStatus.PASS, detail=detail)


@register("deploy")
def deploy_docker(_settings: Settings) -> CheckResult:
    """Docker daemon reachable from this process?"""
    if shutil.which("docker") is None:
        return CheckResult(name="deploy_docker", status=CheckStatus.SKIP, detail="docker not in PATH")
    try:
        rc, out = _run(["docker", "version", "--format", "{{.Server.Version}}"], _DOCKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="deploy_docker",
            status=CheckStatus.FAIL,
            detail="docker daemon probe timed out",
            resolution="Check `docker ps` runs; start Docker Desktop or the docker service",
        )
    if rc != 0:
        return CheckResult(
            name="deploy_docker",
            status=CheckStatus.SKIP,
            detail="docker daemon not reachable from this context",
        )
    return CheckResult(name="deploy_docker", status=CheckStatus.PASS, detail=f"v{out.strip()}")


@register("deploy")
def deploy_compose(_settings: Settings) -> CheckResult:
    """``docker compose config`` parses the project's compose file?"""
    compose_path = next((p for p in _COMPOSE_CANDIDATES if p.exists()), None)
    if compose_path is None:
        return CheckResult(name="deploy_compose", status=CheckStatus.SKIP, detail="no docker-compose.yml found")
    if shutil.which("docker") is None:
        # Fall back to a YAML-parse check so we still catch syntax errors when docker isn't installed.
        try:
            import yaml  # type: ignore[import-untyped]

            with compose_path.open(encoding="utf-8") as f:
                yaml.safe_load(f)
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="deploy_compose",
                status=CheckStatus.FAIL,
                detail=f"{compose_path} invalid: {exc}",
            )
        return CheckResult(name="deploy_compose", status=CheckStatus.PASS, detail=f"{compose_path} parsed (yaml only)")
    try:
        rc, out = _run(["docker", "compose", "-f", str(compose_path), "config", "--quiet"], _DOCKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return CheckResult(
            name="deploy_compose",
            status=CheckStatus.SKIP,
            detail="docker compose probe timed out",
        )
    if rc != 0:
        return CheckResult(
            name="deploy_compose",
            status=CheckStatus.FAIL,
            detail=f"{compose_path} invalid: {out}",
            resolution=f"Run `docker compose -f {compose_path} config` to see the parse error",
        )
    return CheckResult(name="deploy_compose", status=CheckStatus.PASS, detail=f"{compose_path} valid")
