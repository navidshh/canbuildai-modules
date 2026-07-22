"""Public HTTP routes for the Building Energy Code & Standards Assistant.

Endpoints (all under prefix ``/code-assistant`` when registered by the app):
  GET  /knowledge-bases           -> list available code documents + load status
  POST /chat                      -> non-streaming JSON answer (simple clients)
  POST /chat/stream               -> Server-Sent Events streaming answer

All endpoints require a valid Cognito Bearer token, matching the pattern used by
the surrogate and retrofit routers.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..auth.dependency_functions import get_api_user
from ..services.bedrock_rag import BEDROCK_MODEL_ID, get_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    selected_codes: List[str] = Field(
        default_factory=list,
        description="code_ids to search (e.g. ['necb_2020', 'necb_2025']). Empty = all loaded.",
    )
    history: Optional[List[ChatTurn]] = Field(default=None, description="Prior turns for context.")
    top_k: int = Field(default=6, ge=1, le=15)


@router.get("/knowledge-bases")
async def list_knowledge_bases(user: Dict[str, Any] = Depends(get_api_user)):
    svc = get_service()
    return {
        "model_id": BEDROCK_MODEL_ID,
        "ready": svc.is_ready(),
        "knowledge_bases": svc.available_codes(),
    }


@router.get("/health")
async def health():
    """Unauthenticated health check for ALB target-group probes."""
    svc = get_service()
    return {
        "status": "ok" if svc.is_ready() else "loading",
        "model_id": BEDROCK_MODEL_ID,
        "loaded_codes": svc.store.available_codes() if svc.store else [],
    }


@router.post("/chat")
async def chat(req: ChatRequest, user: Dict[str, Any] = Depends(get_api_user)):
    """Non-streaming answer. Convenient for smoke-tests and simple clients."""
    svc = get_service()
    if not svc.is_ready():
        raise HTTPException(status_code=503, detail="Assistant not ready (no indexes loaded)")

    history = [t.dict() for t in req.history] if req.history else None
    citations: List[dict] = []
    parts: List[str] = []
    usage: Dict[str, Any] = {}
    error: Optional[str] = None

    for evt in svc.answer_stream(
        question=req.message,
        selected_codes=req.selected_codes,
        history=history,
        top_k=req.top_k,
    ):
        t = evt.get("type")
        if t == "citations":
            citations = evt["citations"]
        elif t == "delta":
            parts.append(evt["text"])
        elif t == "done":
            usage = evt.get("usage", {})
        elif t == "error":
            error = evt.get("message")
            break

    if error:
        raise HTTPException(status_code=502, detail=error)

    return JSONResponse({
        "answer": "".join(parts),
        "citations": citations,
        "model_id": BEDROCK_MODEL_ID,
        "usage": usage,
    })


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user: Dict[str, Any] = Depends(get_api_user)):
    """Server-Sent Events streaming answer.

    Each event is ``data: <json>\\n\\n`` where ``<json>`` is one of:
      {"type":"citations","citations":[...]}
      {"type":"delta","text":"..."}
      {"type":"done","usage":{...}}
      {"type":"error","message":"..."}
    """
    svc = get_service()
    if not svc.is_ready():
        raise HTTPException(status_code=503, detail="Assistant not ready (no indexes loaded)")

    history = [t.dict() for t in req.history] if req.history else None

    def gen():
        try:
            for evt in svc.answer_stream(
                question=req.message,
                selected_codes=req.selected_codes,
                history=history,
                top_k=req.top_k,
            ):
                yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            logger.exception("Stream generator crashed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
