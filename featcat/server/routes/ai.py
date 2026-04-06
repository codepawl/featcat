"""AI/LLM endpoints: discovery and natural language query."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_db, get_llm, get_settings

router = APIRouter()


class DiscoverRequest(BaseModel):
    use_case: str


class AskRequest(BaseModel):
    query: str


@router.post("/discover")
def discover(body: DiscoverRequest, db=Depends(get_db), llm=Depends(get_llm), settings=Depends(get_settings)):
    """Feature discovery for a use case."""
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is Ollama running?")

    from ...plugins.discovery import DiscoveryPlugin

    plugin = DiscoveryPlugin()
    result = plugin.execute(db, llm, use_case=body.use_case, max_features=settings.max_context_features)

    if result.status == "error":
        raise HTTPException(status_code=500, detail="; ".join(result.errors))

    return result.data


@router.post("/ask")
def ask(body: AskRequest, db=Depends(get_db), llm=Depends(get_llm)):
    """Natural language query about features."""
    from ...plugins.nl_query import NLQueryPlugin

    plugin = NLQueryPlugin()
    fallback = llm is None
    result = plugin.execute(db, llm, query=body.query, fallback_only=fallback)

    if result.status == "error":
        raise HTTPException(status_code=500, detail="; ".join(result.errors))

    return result.data


@router.get("/ask/stream")
async def stream_ask(query: str, db=Depends(get_db), llm=Depends(get_llm)):
    """Streaming NL query via Server-Sent Events."""
    from sse_starlette.sse import EventSourceResponse

    from ...plugins.nl_query import NLQueryPlugin
    from ...utils.catalog_context import get_feature_summary
    from ...utils.prompts import NL_QUERY_PROMPT, NL_QUERY_SYSTEM

    async def event_generator():
        if llm is None:
            plugin = NLQueryPlugin()
            result = plugin.execute(db, llm, query=query, fallback_only=True)
            yield {"event": "message", "data": json.dumps({"type": "done", "data": result.data})}
            return

        feature_summary = get_feature_summary(db, max_features=100)
        from ...utils.lang import detect_language, localize_system_prompt

        lang = detect_language(query)
        system = localize_system_prompt(NL_QUERY_SYSTEM, lang)
        prompt = NL_QUERY_PROMPT.format(feature_summary=feature_summary, query=query)

        full_response = ""
        for token in llm.stream(prompt, system=system):
            full_response += token
            yield {"event": "message", "data": json.dumps({"type": "token", "content": token})}

        from ...llm.base import _extract_json

        parsed = _extract_json(full_response)
        if parsed is None:
            parsed = {"results": [], "interpretation": full_response}

        yield {"event": "message", "data": json.dumps({"type": "done", "data": parsed})}

    return EventSourceResponse(event_generator())
