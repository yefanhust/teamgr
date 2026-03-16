"""Scholar (龙图阁大学士) router — AI Q&A powered by Claude Code CLI."""

import logging
import os
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.middleware.auth_middleware import require_auth
from app.services import scholar_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scholar", tags=["scholar"])


def _utc_iso(dt) -> str | None:
    """Format a UTC datetime as ISO string with Z suffix."""
    if not dt:
        return None
    return dt.isoformat() + "Z"


# ──────────────── Models ────────────────


class AskRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None
    file_ids: list[str] = []


class AskResponse(BaseModel):
    query_id: str
    conversation_id: str


class ScheduledQuestionCreate(BaseModel):
    title: str
    prompt: str
    schedule_type: str = "daily"
    cron_hour: int = 6
    cron_minute: int = 0
    day_of_week: str = "mon"
    day_of_month: int = 1
    depends_on_id: Optional[int] = None
    context_days: int = 7
    enabled: bool = True


class ScheduledQuestionUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    schedule_type: Optional[str] = None
    cron_hour: Optional[int] = None
    cron_minute: Optional[int] = None
    day_of_week: Optional[str] = None
    day_of_month: Optional[int] = None
    depends_on_id: Optional[int] = None
    context_days: Optional[int] = None
    enabled: Optional[bool] = None


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


# ──────────────── Scheduled Questions ────────────────


def _refresh_scholar_scheduler():
    """Refresh per-question APScheduler jobs after any question change."""
    try:
        from app.main import _scheduler
        if _scheduler:
            from app.services.scholar_scheduled_service import refresh_scholar_jobs
            refresh_scholar_jobs(_scheduler)
    except Exception as e:
        logger.warning(f"Failed to refresh scholar scheduler: {e}")


@router.get("/scheduled")
async def list_scheduled_questions(
    _token: str = Depends(require_auth),
):
    """List all scheduled questions with their latest result info."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult
    from sqlalchemy import func

    db = SessionLocal()
    try:
        questions = db.query(ScholarScheduledQuestion).order_by(
            ScholarScheduledQuestion.schedule_type,
            ScholarScheduledQuestion.id,
        ).all()

        result = []
        for q in questions:
            latest = (
                db.query(ScholarScheduledResult)
                .filter(ScholarScheduledResult.question_id == q.id)
                .order_by(ScholarScheduledResult.generated_at.desc())
                .first()
            )
            result_count = (
                db.query(func.count(ScholarScheduledResult.id))
                .filter(ScholarScheduledResult.question_id == q.id)
                .scalar()
            )
            result.append({
                "id": q.id,
                "title": q.title,
                "prompt": q.prompt,
                "schedule_type": q.schedule_type,
                "cron_hour": q.cron_hour,
                "cron_minute": q.cron_minute,
                "day_of_week": q.day_of_week,
                "day_of_month": q.day_of_month,
                "depends_on_id": q.depends_on_id,
                "context_days": q.context_days,
                "enabled": q.enabled,
                "created_at": _utc_iso(q.created_at),
                "result_count": result_count,
                "latest_result": {
                    "id": latest.id,
                    "period_label": latest.period_label,
                    "status": latest.status,
                    "generated_at": _utc_iso(latest.generated_at),
                    "duration_seconds": latest.duration_seconds,
                } if latest else None,
            })

        return result
    finally:
        db.close()


@router.get("/scheduled/results/latest")
async def get_latest_scheduled_results(
    _token: str = Depends(require_auth),
):
    """Get the latest result for each scheduled question."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult

    db = SessionLocal()
    try:
        questions = db.query(ScholarScheduledQuestion).order_by(
            ScholarScheduledQuestion.schedule_type,
            ScholarScheduledQuestion.id,
        ).all()

        result = []
        for q in questions:
            latest = (
                db.query(ScholarScheduledResult)
                .filter(
                    ScholarScheduledResult.question_id == q.id,
                    ScholarScheduledResult.status == "success",
                )
                .order_by(ScholarScheduledResult.generated_at.desc())
                .first()
            )
            if latest:
                result.append({
                    "question_id": q.id,
                    "question_title": q.title,
                    "schedule_type": q.schedule_type,
                    "period_label": latest.period_label,
                    "answer": latest.answer,
                    "generated_at": _utc_iso(latest.generated_at),
                })

        return result
    finally:
        db.close()


@router.post("/scheduled")
async def create_scheduled_question(
    body: ScheduledQuestionCreate,
    _token: str = Depends(require_auth),
):
    """Create a new scheduled question."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion

    if body.schedule_type not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=400, detail="schedule_type 必须是 daily/weekly/monthly")

    db = SessionLocal()
    try:
        q = ScholarScheduledQuestion(
            title=body.title,
            prompt=body.prompt,
            schedule_type=body.schedule_type,
            cron_hour=body.cron_hour,
            cron_minute=body.cron_minute,
            day_of_week=body.day_of_week,
            day_of_month=body.day_of_month,
            depends_on_id=body.depends_on_id,
            context_days=body.context_days,
            enabled=body.enabled,
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        _refresh_scholar_scheduler()
        return {"id": q.id, "title": q.title}
    finally:
        db.close()


@router.put("/scheduled/{question_id}")
async def update_scheduled_question(
    question_id: int,
    body: ScheduledQuestionUpdate,
    _token: str = Depends(require_auth),
):
    """Update a scheduled question."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id
        ).first()
        if not q:
            raise HTTPException(status_code=404, detail="定时问题不存在")

        update_data = body.model_dump(exclude_unset=True)
        if "schedule_type" in update_data and update_data["schedule_type"] not in ("daily", "weekly", "monthly"):
            raise HTTPException(status_code=400, detail="schedule_type 必须是 daily/weekly/monthly")

        for field, value in update_data.items():
            setattr(q, field, value)
        db.commit()
        _refresh_scholar_scheduler()
        return {"ok": True, "id": q.id}
    finally:
        db.close()


@router.delete("/scheduled/{question_id}")
async def delete_scheduled_question(
    question_id: int,
    _token: str = Depends(require_auth),
):
    """Delete a scheduled question and its results."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id
        ).first()
        if not q:
            raise HTTPException(status_code=404, detail="定时问题不存在")
        db.delete(q)
        db.commit()
        _refresh_scholar_scheduler()
        return {"ok": True}
    finally:
        db.close()


@router.post("/scheduled/{question_id}/run")
async def run_scheduled_question(
    question_id: int,
    body: dict = {},
    _token: str = Depends(require_auth),
):
    """Manually trigger a scheduled question. Runs in background thread."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledQuestion, ScholarScheduledResult
    from app.services.scholar_scheduled_service import run_single_question_now, _get_period_label

    force = body.get("force", False)

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id
        ).first()
        if not q:
            raise HTTPException(status_code=404, detail="定时问题不存在")

        # Check for existing result before spawning thread
        if not force:
            period_label = _get_period_label(q.schedule_type)
            existing = (
                db.query(ScholarScheduledResult)
                .filter(
                    ScholarScheduledResult.question_id == q.id,
                    ScholarScheduledResult.period_label == period_label,
                    ScholarScheduledResult.status == "success",
                )
                .first()
            )
            if existing:
                return {
                    "ok": True,
                    "skipped": True,
                    "period_label": period_label,
                    "message": f"本周期（{period_label}）已有结果，如需重新执行请使用「强制执行」",
                }
    finally:
        db.close()

    # Run in background thread to avoid blocking
    def _run():
        try:
            result = run_single_question_now(question_id, force=force)
            logger.info(f"Manual scholar scheduled run complete: {result}")
        except Exception as e:
            logger.error(f"Manual scholar scheduled run failed: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"ok": True, "skipped": False, "message": "已开始执行"}


@router.get("/scheduled/{question_id}/progress")
async def get_execution_progress(
    question_id: int,
    _token: str = Depends(require_auth),
):
    """Get execution progress for a running scheduled question."""
    from app.services.scholar_scheduled_service import get_execution_progress
    return get_execution_progress(question_id)


@router.get("/scheduled/{question_id}/results")
async def get_scheduled_results(
    question_id: int,
    limit: int = 20,
    offset: int = 0,
    _token: str = Depends(require_auth),
):
    """Get results for a scheduled question."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledResult, ScholarScheduledQuestion

    db = SessionLocal()
    try:
        q = db.query(ScholarScheduledQuestion).filter(
            ScholarScheduledQuestion.id == question_id
        ).first()
        if not q:
            raise HTTPException(status_code=404, detail="定时问题不存在")

        results = (
            db.query(ScholarScheduledResult)
            .filter(ScholarScheduledResult.question_id == question_id)
            .order_by(ScholarScheduledResult.generated_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "question": {"id": q.id, "title": q.title, "schedule_type": q.schedule_type},
            "results": [{
                "id": r.id,
                "period_label": r.period_label,
                "answer": r.answer,
                "status": r.status,
                "generated_at": _utc_iso(r.generated_at),
                "duration_seconds": r.duration_seconds,
                "tts_ready": r.status == "success" and bool(r.answer and r.answer.strip()) and os.path.exists(get_tts_cache_path(r.answer)),
            } for r in results],
        }
    finally:
        db.close()


# ──────────────── TTS (Text-to-Speech via edge-tts) ────────────────

from app.services.tts_service import strip_markdown, generate_tts_cache_async, get_tts_cache_path


@router.get("/scheduled/results/{result_id}/tts")
async def get_result_tts(
    result_id: int,
    token: str = "",
):
    """Generate TTS audio for a scheduled result using edge-tts (cached).
    Auth via query param 'token' (for <audio src> which can't set headers).
    """
    from app.middleware.auth_middleware import verify_token
    if not token or not verify_token(token):
        raise HTTPException(status_code=401, detail="认证失败")
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledResult

    db = SessionLocal()
    try:
        r = db.query(ScholarScheduledResult).filter(
            ScholarScheduledResult.id == result_id,
        ).first()
        if not r:
            raise HTTPException(status_code=404, detail="结果不存在")
        answer = r.answer or ""
    finally:
        db.close()

    if not answer.strip():
        raise HTTPException(status_code=400, detail="结果内容为空")

    cache_path = await generate_tts_cache_async(answer)
    if not cache_path:
        raise HTTPException(status_code=500, detail="语音生成失败")

    return FileResponse(
        cache_path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )
