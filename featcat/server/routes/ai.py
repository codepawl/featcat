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

    from ...plugins.nl_query import NLQueryPlugin, _is_monitoring_query
    from ...utils.catalog_context import get_feature_summary, get_monitoring_summary
    from ...utils.prompts import NL_QUERY_PROMPT, NL_QUERY_SYSTEM

    async def event_generator():
        if llm is None:
            plugin = NLQueryPlugin()
            result = plugin.execute(db, llm, query=query, fallback_only=True)
            yield {"event": "message", "data": json.dumps({"type": "result", "content": result.data})}
            yield {"event": "message", "data": json.dumps({"type": "done"})}
            return

        feature_summary = get_feature_summary(db, max_features=100)

        # Add monitoring context for drift-related queries
        extra_context = ""
        if _is_monitoring_query(query):
            extra_context = "\n\nMONITORING STATUS:\n" + get_monitoring_summary(db)

        from ...utils.lang import detect_language, localize_system_prompt

        lang = detect_language(query)
        system = localize_system_prompt(NL_QUERY_SYSTEM, lang)
        prompt = NL_QUERY_PROMPT.format(feature_summary=feature_summary + extra_context, query=query)

        full_response = ""
        buffer = ""
        in_thinking = False

        for token in llm.stream(prompt, system=system):
            buffer += token
            full_response += token

            # Detect <think> start
            if not in_thinking and "<think>" in buffer:
                in_thinking = True
                yield {"event": "message", "data": json.dumps({"type": "thinking_start"})}
                # Drop everything up to and including <think>
                buffer = buffer.split("<think>", 1)[1]
                if not buffer:
                    continue

            # Detect </think> end
            if in_thinking and "</think>" in buffer:
                thinking_text = buffer.split("</think>", 1)[0]
                if thinking_text:
                    yield {"event": "message", "data": json.dumps({"type": "thinking", "content": thinking_text})}
                yield {"event": "message", "data": json.dumps({"type": "thinking_end"})}
                buffer = buffer.split("</think>", 1)[1]
                in_thinking = False
                # Emit any remaining buffer as answer token
                if buffer.strip():
                    yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}
                    buffer = ""
                continue

            if in_thinking:
                # Emit thinking content periodically to avoid huge buffers
                if len(buffer) > 50:
                    yield {"event": "message", "data": json.dumps({"type": "thinking", "content": buffer})}
                    buffer = ""
            else:
                # Emit answer tokens immediately (but hold back if we might be
                # seeing the start of a <think> tag at the very beginning)
                if buffer and "<" not in buffer:
                    yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}
                    buffer = ""
                elif len(buffer) > 10:
                    # Buffer is long enough that it's not a partial <think> tag
                    yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}
                    buffer = ""

        # Flush remaining buffer
        if buffer.strip():
            if in_thinking:
                yield {"event": "message", "data": json.dumps({"type": "thinking", "content": buffer})}
                yield {"event": "message", "data": json.dumps({"type": "thinking_end"})}
            else:
                yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}

        # Parse final response (strip thinking) and send structured result
        from ...llm.base import _extract_json, strip_thinking_tags

        clean_response = strip_thinking_tags(full_response)
        parsed = _extract_json(clean_response)
        if parsed is not None:
            yield {"event": "message", "data": json.dumps({"type": "result", "content": parsed})}

        yield {"event": "message", "data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())
