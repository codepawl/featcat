"""Tests for the setup wizard's environment detection helpers."""

from __future__ import annotations

import shutil
from unittest.mock import patch

from featcat.setup.detect import EnvReport, detect_environment, is_port_free


def test_detect_environment_returns_report() -> None:
    report = detect_environment()
    assert isinstance(report, EnvReport)
    assert report.python_version.startswith("3.")


def test_is_port_free_for_random_high_port() -> None:
    assert is_port_free(54321) is True


def test_detect_environment_reports_no_docker_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    report = detect_environment()
    assert report.docker_path is None
    assert report.docker_available is False


def test_detect_environment_reports_docker_when_present(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with patch("featcat.setup.detect.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        report = detect_environment()
    assert report.docker_path == "/usr/bin/docker"
    assert report.docker_available is True


def test_detect_environment_handles_docker_info_failure(monkeypatch) -> None:
    """When `docker info` returns non-zero, treat docker as unavailable."""
    monkeypatch.setattr(shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with patch("featcat.setup.detect.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        report = detect_environment()
    assert report.docker_path == "/usr/bin/docker"
    assert report.docker_available is False
