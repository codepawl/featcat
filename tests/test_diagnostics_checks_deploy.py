"""Tests for ``featcat.diagnostics.checks_deploy``.

These run the actual ``git`` / ``docker`` binaries when available — the cwd
during ``make test`` is the repo root, so ``deploy_git`` exercises the real
working tree. The ``docker`` and compose checks must remain SKIP-safe on
systems without Docker (CI runners, fresh laptops); tests below verify that.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from featcat.config import Settings
from featcat.diagnostics import CheckStatus
from featcat.diagnostics.checks_deploy import deploy_compose, deploy_docker, deploy_git

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def settings() -> Settings:
    return Settings()


class TestDeployGit:
    def test_skip_when_outside_working_tree(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        settings: Settings,
    ) -> None:
        """When run from a directory without .git/, the check must SKIP, not FAIL."""
        monkeypatch.chdir(tmp_path)
        result = deploy_git(settings)
        assert result.status is CheckStatus.SKIP

    def test_skip_when_git_missing(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        result = deploy_git(settings)
        assert result.status is CheckStatus.SKIP


class TestDeployDocker:
    def test_skip_when_docker_missing(self, monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        result = deploy_docker(settings)
        assert result.status is CheckStatus.SKIP

    def test_runs_when_docker_present(self, settings: Settings) -> None:
        """If docker is installed we expect a PASS or SKIP — never FAIL.

        FAIL would mean the daemon timed out; that's a real failure mode but
        we don't want this test flaky. The check returns SKIP rather than
        FAIL when the daemon is unreachable, so PASS/SKIP is the full set
        of acceptable outcomes here.
        """
        result = deploy_docker(settings)
        assert result.status in {CheckStatus.PASS, CheckStatus.SKIP}


class TestDeployCompose:
    def test_skip_when_no_compose_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        settings: Settings,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = deploy_compose(settings)
        assert result.status is CheckStatus.SKIP

    def test_runs_on_real_repo(self, settings: Settings) -> None:
        """Run from repo root — `deploy/docker-compose.yml` exists and is valid."""
        result = deploy_compose(settings)
        if shutil.which("docker") is None:
            # YAML-only fallback path — file exists and parses → PASS.
            assert result.status is CheckStatus.PASS
        else:
            # Either PASS (docker daemon valid) or SKIP (timeout) — never FAIL on the real file.
            assert result.status in {CheckStatus.PASS, CheckStatus.SKIP}
