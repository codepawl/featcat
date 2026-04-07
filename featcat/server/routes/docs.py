"""Documentation endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..deps import get_db, get_llm

router = APIRouter()

LLM_TIMEOUT = 180


class DocGenerateRequest(BaseModel):
    feature_name: str | None = None


@router.post("/generate")
async def generate_docs(body: DocGenerateRequest, db=Depends(get_db), llm=Depends(get_llm)):
    """Generate AI documentation for features."""
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is Ollama running?")

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


@router.get("/stats")
def doc_stats(db=Depends(get_db)):
    """Documentation coverage statistics."""
    return db.get_doc_stats()


@router.get("/by-name")
def get_doc_by_name(name: str = Query(...), db=Depends(get_db)):
    """Get documentation for a specific feature (query param for dotted names)."""
    from ...plugins.autodoc import get_doc as _get_doc

    doc = _get_doc(db, name)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No docs for: {name}")
    return doc
