"""Documentation endpoints."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..deps import get_db, get_llm

router = APIRouter()
logger = logging.getLogger(__name__)

LLM_TIMEOUT = 180

# In-memory batch job tracking. Per-process only — works for single-worker
# and dev proxy setups. For multi-worker production, use DB-backed jobs.
_batch_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


class DocGenerateRequest(BaseModel):
    feature_name: str | None = None


@router.post("/generate")
async def generate_docs(body: DocGenerateRequest, db=Depends(get_db), llm=Depends(get_llm)):
    """Generate AI documentation for features."""
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is LLM server running?")

    from ...plugins.autodoc import AutodocPlugin

    plugin = AutodocPlugin()
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(plugin.execute, db, llm, feature_name=body.feature_name),
            timeout=LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return {"documented": 0, "total": 0, "error": "Request timed out. LLM is slow."}

    if result.status == "error":
        raise HTTPException(status_code=500, detail="; ".join(result.errors))

    return result.data


# --- Batch generation ---


class BatchGenerateRequest(BaseModel):
    feature_specs: list[str]
    regenerate_existing: bool = False
    global_hint: str | None = None


@router.post("/generate-batch")
def generate_batch(
    body: BatchGenerateRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),  # noqa: B008
    llm=Depends(get_llm),  # noqa: B008
):
    """Start batch doc generation as a background task."""
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is LLM server running?")

    if not body.feature_specs:
        raise HTTPException(status_code=400, detail="feature_specs must not be empty")

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _batch_jobs[job_id] = {
            "job_id": job_id,
            "total": len(body.feature_specs),
            "completed": 0,
            "failed": 0,
            "status": "running",
        }

    background_tasks.add_task(
        _run_batch_generation,
        job_id=job_id,
        feature_specs=body.feature_specs,
        global_hint=body.global_hint,
        db=db,
        llm=llm,
    )

    return {"job_id": job_id, "total": len(body.feature_specs)}


@router.get("/generate-batch/{job_id}/status")
def batch_status(job_id: str):
    """Poll batch generation progress."""
    with _jobs_lock:
        job = _batch_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _run_batch_generation(
    job_id: str,
    feature_specs: list[str],
    global_hint: str | None,
    db: object,
    llm: object,
) -> None:
    """Background task: generate docs for each feature sequentially."""
    from ...plugins.autodoc import AutodocPlugin
    from ...utils.lang import localize_system_prompt
    from ...utils.prompts import AUTODOC_SYSTEM

    plugin = AutodocPlugin()
    system = localize_system_prompt(AUTODOC_SYSTEM, "en")

    for spec in feature_specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            with _jobs_lock:
                _batch_jobs[job_id]["failed"] += 1
            logger.warning("Batch %s: feature not found: %s", job_id, spec)
            continue

        # Temporarily inject global hint for features without an individual hint
        original_hint = feature.generation_hints
        if global_hint and not feature.generation_hints:
            feature.generation_hints = global_hint

        try:
            doc = plugin._generate_one(db, llm, feature, system)
            with _jobs_lock:
                if doc:
                    _batch_jobs[job_id]["completed"] += 1
                else:
                    _batch_jobs[job_id]["failed"] += 1
        except Exception as e:
            logger.error("Batch %s: failed for %s: %s", job_id, spec, e)
            with _jobs_lock:
                _batch_jobs[job_id]["failed"] += 1
        finally:
            feature.generation_hints = original_hint

    with _jobs_lock:
        _batch_jobs[job_id]["status"] = "done"

    logger.info("Batch %s complete: %s", job_id, _batch_jobs[job_id])


# --- Stats and lookup ---


@router.get("/stats")
def doc_stats(db=Depends(get_db)):
    """Documentation coverage statistics."""
    return db.get_doc_stats()


@router.get("/by-name")
def get_doc_by_name(name: str = Query(...), db=Depends(get_db)):
    """Get documentation for a specific feature (query param for dotted names)."""
    from ...plugins.autodoc import get_doc as _get_doc

    doc = _get_doc(db, name)
    return doc
