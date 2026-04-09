"""AI/LLM endpoints: discovery and natural language query."""

from __future__ import annotations

import asyncio
import json
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..deps import get_db, get_llm, get_settings

router = APIRouter()

LLM_TIMEOUT = 180  # 3 minutes max for LLM calls

_THINKING_KEYWORDS = frozenset(
    ["discover", "analyze", "why", "explain", "compare", "recommend", "suggest", "strategy", "tại sao", "phân tích"]
)


def _needs_thinking(query: str) -> bool:
    q = query.lower()
    return any(kw in q for kw in _THINKING_KEYWORDS)


class DiscoverRequest(BaseModel):
    use_case: str


class AskRequest(BaseModel):
    query: str


@router.post("/discover")
async def discover(body: DiscoverRequest, db=Depends(get_db), llm=Depends(get_llm), settings=Depends(get_settings)):
    """Feature discovery for a use case."""
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is LLM server running?")

    from ...plugins.discovery import DiscoveryPlugin

    plugin = DiscoveryPlugin()
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(
                plugin.execute, db, llm, use_case=body.use_case, max_features=settings.max_context_features
            ),
            timeout=LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return {"existing_features": [], "new_feature_suggestions": [], "summary": "Request timed out. LLM is slow."}

    if result.status == "error":
        raise HTTPException(status_code=500, detail="; ".join(result.errors))

    return result.data


@router.post("/ask")
async def ask(body: AskRequest, db=Depends(get_db), llm=Depends(get_llm)):
    """Natural language query about features."""
    from ...plugins.nl_query import NLQueryPlugin

    plugin = NLQueryPlugin()
    fallback = llm is None
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(plugin.execute, db, llm, query=body.query, fallback_only=fallback),
            timeout=LLM_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return {"results": [], "interpretation": "Request timed out. LLM is slow on CPU.", "method": "timeout"}

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
            result = await run_in_threadpool(plugin.execute, db, llm, query=query, fallback_only=True)
            yield {"event": "message", "data": json.dumps({"type": "result", "content": result.data})}
            yield {"event": "message", "data": json.dumps({"type": "done"})}
            return

        feature_summary = await run_in_threadpool(get_feature_summary, db, max_features=100)

        # Add monitoring context for drift-related queries
        extra_context = ""
        if _is_monitoring_query(query):
            extra_context = "\n\nMONITORING STATUS:\n" + await run_in_threadpool(get_monitoring_summary, db)

        from ...utils.lang import detect_language, localize_system_prompt

        lang = detect_language(query)
        system = localize_system_prompt(NL_QUERY_SYSTEM, lang)
        prompt = NL_QUERY_PROMPT.format(feature_summary=feature_summary + extra_context, query=query)

        full_response = ""
        buffer = ""
        in_thinking = False

        try:
            # Run sync LLM stream in a background thread to avoid blocking the event loop
            think = _needs_thinking(query)
            queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_event_loop()

            def _run_stream():
                try:
                    for tok in llm.stream(prompt, system=system, think=think):
                        asyncio.run_coroutine_threadsafe(queue.put(tok), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(None), loop)
                except Exception as exc:
                    asyncio.run_coroutine_threadsafe(queue.put(exc), loop)

            thread = threading.Thread(target=_run_stream, daemon=True)
            thread.start()

            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                token = item
                buffer += token
                full_response += token

                # Detect <think> start
                if not in_thinking and "<think>" in buffer:
                    in_thinking = True
                    yield {"event": "message", "data": json.dumps({"type": "thinking_start"})}
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
                    if buffer.strip():
                        yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}
                        buffer = ""
                    continue

                if in_thinking:
                    if len(buffer) > 50:
                        yield {"event": "message", "data": json.dumps({"type": "thinking", "content": buffer})}
                        buffer = ""
                else:
                    if buffer and "<" not in buffer or len(buffer) > 10:
                        yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}
                        buffer = ""

            # Flush remaining buffer
            if buffer.strip():
                if in_thinking:
                    yield {"event": "message", "data": json.dumps({"type": "thinking", "content": buffer})}
                    yield {"event": "message", "data": json.dumps({"type": "thinking_end"})}
                else:
                    yield {"event": "message", "data": json.dumps({"type": "token", "content": buffer})}

            # Parse final response and send structured result
            from ...llm.base import _extract_json, strip_thinking_tags

            clean_response = strip_thinking_tags(full_response)
            parsed = _extract_json(clean_response)
            if parsed is not None:
                yield {"event": "message", "data": json.dumps({"type": "result", "content": parsed})}

        except Exception as e:
            yield {"event": "message", "data": json.dumps({"type": "error", "content": str(e)})}

        yield {"event": "message", "data": json.dumps({"type": "done"})}

    return EventSourceResponse(event_generator())
