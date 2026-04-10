"""Tests for the job API endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from featcat.server.app import build_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    return build_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestJobList:
    def test_list_jobs(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        names = [j["job_name"] for j in data]
        assert "monitor_check" in names

    def test_list_has_cron(self, client):
        resp = client.get("/api/jobs")
        job = resp.json()[0]
        assert "cron_expression" in job
        assert "enabled" in job


class TestJobRun:
    def test_run_job(self, client):
        resp = client.post("/api/jobs/baseline_refresh/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "warning")
        assert data["job_name"] == "baseline_refresh"

    def test_run_unknown_job(self, client):
        resp = client.post("/api/jobs/nonexistent/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"


class TestJobLogs:
    def test_logs_empty(self, client):
        resp = client.get("/api/jobs/logs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_logs_after_run(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) == 1

    def test_logs_filter_by_job(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/logs?job_name=monitor_check")
        assert resp.json() == []
        resp = client.get("/api/jobs/logs?job_name=baseline_refresh")
        assert len(resp.json()) == 1

    def test_log_detail(self, client):
        run_resp = client.post("/api/jobs/baseline_refresh/run")
        log_id = run_resp.json()["id"]
        resp = client.get(f"/api/jobs/logs/{log_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == log_id


class TestJobUpdate:
    def test_update_cron(self, client):
        resp = client.patch("/api/jobs/monitor_check", json={"cron_expression": "0 */3 * * *"})
        assert resp.status_code == 200
        jobs = client.get("/api/jobs").json()
        mc = next(j for j in jobs if j["job_name"] == "monitor_check")
        assert mc["cron_expression"] == "0 */3 * * *"

    def test_disable_job(self, client):
        resp = client.patch("/api/jobs/monitor_check", json={"enabled": False})
        assert resp.status_code == 200
        jobs = client.get("/api/jobs").json()
        mc = next(j for j in jobs if j["job_name"] == "monitor_check")
        assert mc["enabled"] == 0


class TestJobStats:
    def test_stats_structure(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        assert "baseline_refresh" in data["jobs"]
        br = data["jobs"]["baseline_refresh"]
        assert br["total_runs"] == 1
        assert "sparkline" in br
        assert len(br["sparkline"]) == 7
