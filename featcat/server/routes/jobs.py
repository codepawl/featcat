"""Job scheduler API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_scheduler

router = APIRouter()


class JobUpdate(BaseModel):
    cron_expression: str | None = None
    enabled: bool | None = None


@router.get("")
def list_jobs(scheduler=Depends(get_scheduler)):
    """List all job schedules."""
    if scheduler is None:
        return []
    return scheduler.get_schedules()


@router.get("/logs")
def list_logs(
    job_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scheduler=Depends(get_scheduler),
):
    """List recent job execution logs."""
    if scheduler is None:
        return []
    return scheduler.get_logs(job_name=job_name, status=status, limit=limit, offset=offset)


@router.get("/logs/{log_id}")
def get_log(log_id: str, scheduler=Depends(get_scheduler)):
    """Get details of a single job execution."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    log = scheduler.get_log(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail=f"Log not found: {log_id}")
    return log


@router.post("/{name}/run")
async def run_job(name: str, scheduler=Depends(get_scheduler)):
    """Manually trigger a job."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    result = await scheduler.run_job(name, triggered_by="api")
    return result


@router.patch("/{name}")
def update_job(name: str, body: JobUpdate, scheduler=Depends(get_scheduler)):
    """Update a job's schedule or enabled state."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    schedules = scheduler.get_schedules()
    names = [s["job_name"] for s in schedules]
    if name not in names:
        raise HTTPException(status_code=404, detail=f"Job not found: {name}")
    scheduler.update_schedule(name, cron=body.cron_expression, enabled=body.enabled)
    return {"updated": name}


@router.get("/stats")
def job_stats(scheduler=Depends(get_scheduler)):
    """Aggregated job stats with sparkline data."""
    if scheduler is None:
        return {"jobs": {}}
    return scheduler.get_stats()
