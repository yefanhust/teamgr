"""Scholar (龙图阁大学士) router — AI Q&A powered by Claude Code CLI."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.middleware.auth_middleware import require_auth
from app.services import scholar_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scholar", tags=["scholar"])


# ──────────────── Models ────────────────


class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    file_ids: list[str] = []


class AskResponse(BaseModel):
    query_id: str
    conversation_id: str


# ──────────────── Endpoints ────────────────


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _token: str = Depends(require_auth),
):
    """Upload a PDF or text file for scholar context."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="文件大小不能超过50MB")

    result = scholar_service.save_uploaded_file(file.filename, content)
    return result


@router.post("/ask", response_model=AskResponse)
async def ask_scholar(
    body: AskRequest,
    _token: str = Depends(require_auth),
):
    """Submit a question to the scholar. Returns query_id for stream subscription."""
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    query_id = scholar_service.gen_id()
    conversation_id = body.conversation_id or scholar_service.gen_id()

    # Look up existing session for conversation continuity
    session_id = scholar_service.get_conversation_session_id(conversation_id)

    # Write signal file for watcher
    scholar_service.write_query_signal(
        query_id=query_id,
        question=body.question.strip(),
        conversation_id=conversation_id,
        session_id=session_id,
        file_ids=body.file_ids,
    )

    # Update conversation record
    scholar_service.create_or_update_conversation(
        conversation_id=conversation_id,
        query_id=query_id,
        question=body.question.strip(),
        file_ids=body.file_ids,
    )

    return AskResponse(query_id=query_id, conversation_id=conversation_id)


@router.get("/stream/{query_id}")
async def stream_scholar(
    query_id: str,
    _token: str = Depends(require_auth),
):
    """SSE endpoint: stream Claude's response for a given query."""
    conversation_id = scholar_service.find_conversation_id_by_query(query_id)
    return StreamingResponse(
        scholar_service.stream_response(query_id, conversation_id=conversation_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations")
async def get_conversations(
    _token: str = Depends(require_auth),
):
    """List all scholar conversations."""
    return scholar_service.list_conversations()


@router.get("/conversations/categorized")
async def get_categorized_conversations(
    _token: str = Depends(require_auth),
):
    """List conversations categorized by topic using LLM."""
    return await scholar_service.categorize_conversations()


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    _token: str = Depends(require_auth),
):
    """Get a specific conversation with messages."""
    conv = scholar_service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    _token: str = Depends(require_auth),
):
    """Delete a conversation."""
    if scholar_service.delete_conversation(conversation_id):
        return {"ok": True}
    raise HTTPException(status_code=404, detail="对话不存在")
