import asyncio
import json
import logging
import re
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db, SessionLocal
from app.models.talent import DiaryEntry, DiaryTag, DiaryEntryTag
from app.config import get_diary_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diary", tags=["diary"])


# ---- Pydantic schemas ----

class DiaryPasswordVerify(BaseModel):
    password: str


class DiaryEntryCreate(BaseModel):
    title: Optional[str] = None
    content: str
    diary_date: Optional[str] = None  # "YYYY-MM-DD", defaults to today
    tag_ids: Optional[list[int]] = None


class DiaryEntryUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    diary_date: Optional[str] = None
    tag_ids: Optional[list[int]] = None


class DiaryTagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


# ---- Password verification dependency ----

def _verify_diary_password(request: Request):
    """Check X-Diary-Password header against configured password."""
    configured = get_diary_password()
    if not configured:
        raise HTTPException(status_code=403, detail="手记功能未配置密码")
    password = request.headers.get("X-Diary-Password", "")
    if password != configured:
        raise HTTPException(status_code=403, detail="手记密码错误")
    return True


# ---- Serialization ----

def _serialize_entry(entry: DiaryEntry) -> dict:
    return {
        "id": entry.id,
        "title": entry.title or "",
        "content": entry.content,
        "diary_date": entry.diary_date,
        "llm_comment": entry.llm_comment,
        "commented_at": entry.commented_at.isoformat() if entry.commented_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in entry.tags],
    }


# ---- Password verification endpoint ----

@router.post("/verify-password")
def verify_password(body: DiaryPasswordVerify):
    configured = get_diary_password()
    if not configured:
        raise HTTPException(status_code=403, detail="手记功能未配置密码")
    return {"verified": body.password == configured}


# ---- Entry CRUD ----

@router.get("/entries")
def list_entries(
    page: int = 1,
    page_size: int = 20,
    tag_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    query = db.query(DiaryEntry)
    if tag_id:
        query = query.filter(DiaryEntry.tags.any(DiaryTag.id == tag_id))
    total = query.count()
    entries = (
        query.order_by(DiaryEntry.diary_date.desc(), DiaryEntry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "entries": [_serialize_entry(e) for e in entries],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/entries")
async def create_entry(
    body: DiaryEntryCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    diary_date = body.diary_date or date.today().isoformat()
    entry = DiaryEntry(
        title=body.title,
        content=body.content,
        diary_date=diary_date,
    )
    db.add(entry)
    db.flush()

    # Assign manually selected tags
    if body.tag_ids:
        for tid in body.tag_ids:
            tag = db.query(DiaryTag).filter(DiaryTag.id == tid).first()
            if tag:
                db.add(DiaryEntryTag(entry_id=entry.id, tag_id=tag.id))

    db.commit()
    db.refresh(entry)

    # Async auto-tag in background
    entry_id = entry.id
    content = body.content
    asyncio.create_task(_diary_auto_tag_bg(entry_id, content))

    return _serialize_entry(entry)


@router.put("/entries/{entry_id}")
async def update_entry(
    entry_id: int,
    body: DiaryEntryUpdate,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="手记不存在")

    content_changed = False
    if body.title is not None:
        entry.title = body.title
    if body.content is not None and body.content != entry.content:
        entry.content = body.content
        content_changed = True
    if body.diary_date is not None:
        entry.diary_date = body.diary_date

    # Update tag associations
    if body.tag_ids is not None:
        db.query(DiaryEntryTag).filter(DiaryEntryTag.entry_id == entry_id).delete()
        for tid in body.tag_ids:
            tag = db.query(DiaryTag).filter(DiaryTag.id == tid).first()
            if tag:
                db.add(DiaryEntryTag(entry_id=entry_id, tag_id=tag.id))

    db.commit()
    db.refresh(entry)

    # Re-tag if content changed
    if content_changed:
        asyncio.create_task(_diary_auto_tag_bg(entry_id, entry.content))

    return _serialize_entry(entry)


@router.delete("/entries/{entry_id}")
def delete_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="手记不存在")
    db.query(DiaryEntryTag).filter(DiaryEntryTag.entry_id == entry_id).delete()
    db.delete(entry)
    db.commit()
    return {"message": "已删除"}


# ---- Tag CRUD ----

@router.get("/tags")
def list_tags(
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    tags = db.query(DiaryTag).order_by(DiaryTag.name).all()
    return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]


@router.post("/tags")
def create_tag(
    body: DiaryTagCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    existing = db.query(DiaryTag).filter(DiaryTag.name == body.name).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "color": existing.color}
    tag = DiaryTag(name=body.name, color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.put("/tags/{tag_id}")
def update_tag(
    tag_id: int,
    body: DiaryTagCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    tag = db.query(DiaryTag).filter(DiaryTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if body.name and body.name != tag.name:
        dup = db.query(DiaryTag).filter(DiaryTag.name == body.name, DiaryTag.id != tag_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="标签名已存在")
        tag.name = body.name
    if body.color:
        tag.color = body.color
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.delete("/tags/{tag_id}")
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    tag = db.query(DiaryTag).filter(DiaryTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.query(DiaryEntryTag).filter(DiaryEntryTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()
    return {"message": "已删除"}


# ---- LLM helpers (local model only) ----

def _get_local_only_config(call_type: str) -> dict | None:
    """Get local model config for a diary call type. Returns None if not local."""
    from app.config import get_model_defaults, get_local_models_config
    from app.services.llm_service import _get_local_model_config

    model_name = get_model_defaults().get(call_type)
    if not model_name:
        # Fallback to first local model
        local_models = get_local_models_config()
        if local_models:
            model_name = local_models[0].get("name")
    if not model_name:
        return None

    local_cfg = _get_local_model_config(model_name)
    if not local_cfg:
        logger.warning(f"Diary {call_type}: model '{model_name}' is not a local model, skipping")
        return None
    return local_cfg


async def _call_local_only(prompt: str, call_type: str) -> str | None:
    """Call local LLM only. Returns text or None if no local model available."""
    local_cfg = _get_local_only_config(call_type)
    if not local_cfg:
        return None

    from app.services.llm_service import _call_local_model, _record_llm_usage
    import time

    model_name = local_cfg.get("name", "local")
    t0 = time.monotonic()
    try:
        text, isl, osl = await _call_local_model(prompt, local_cfg)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Local {model_name} {call_type}: {duration_ms}ms (ISL={isl}, OSL={osl})")
        _record_llm_usage(model_name, call_type, duration_ms, isl, osl)
        return text
    except Exception as e:
        logger.error(f"Diary LLM call failed ({call_type}): {e}")
        return None


# ---- Auto-tag ----

async def _diary_auto_tag_bg(entry_id: int, content: str):
    """Background task: auto-tag a diary entry using local LLM."""
    try:
        tag_names = await _diary_auto_tag(content)
        if not tag_names:
            return
        db = SessionLocal()
        try:
            entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
            if not entry:
                return
            for name in tag_names:
                tag = db.query(DiaryTag).filter(DiaryTag.name == name).first()
                if not tag:
                    tag = DiaryTag(name=name)
                    db.add(tag)
                    db.flush()
                existing = db.query(DiaryEntryTag).filter(
                    DiaryEntryTag.entry_id == entry_id,
                    DiaryEntryTag.tag_id == tag.id,
                ).first()
                if not existing:
                    db.add(DiaryEntryTag(entry_id=entry_id, tag_id=tag.id))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Diary auto-tag failed for entry {entry_id}: {e}")


async def _diary_auto_tag(content: str) -> list[str]:
    """Use local LLM to generate 1-3 short tags for a diary entry."""
    prompt = f"""为以下手记内容生成1-3个简短的分类标签（每个标签2-4个字）。
标签应反映手记的主题或领域（如"工作思考"、"生活感悟"、"技术探索"、"读书笔记"、"人际关系"等）。

手记内容：{content[:500]}

请严格按JSON数组格式返回标签列表，不要包含其他内容：
["标签1", "标签2"]"""

    text = await _call_local_only(prompt, "diary-auto-tag")
    if not text:
        return []
    try:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        tags = json.loads(text)
        if isinstance(tags, list):
            return [str(t).strip() for t in tags if str(t).strip()][:3]
    except Exception as e:
        logger.warning(f"Diary auto-tag parse failed: {e}")
    return []


# ---- Daily comment job ----

async def run_daily_diary_comment():
    """Run by scheduler. Generates AI comments for today's uncommented entries."""
    db = SessionLocal()
    try:
        today = date.today().isoformat()
        entries = db.query(DiaryEntry).filter(
            DiaryEntry.diary_date == today,
            DiaryEntry.llm_comment.is_(None),
        ).all()

        if not entries:
            logger.info("Diary comment: no uncommented entries for today")
            return

        logger.info(f"Diary comment: processing {len(entries)} entries")
        for entry in entries:
            comment = await _generate_diary_comment(entry.content)
            if comment:
                entry.llm_comment = comment
                entry.commented_at = datetime.utcnow()
                db.commit()
                logger.info(f"Diary comment: generated for entry {entry.id}")
    except Exception as e:
        logger.error(f"Diary daily comment job failed: {e}")
    finally:
        db.close()


async def _generate_diary_comment(content: str) -> str | None:
    """Generate a warm, supportive AI comment for a diary entry."""
    prompt = f"""你是一位温暖、有洞察力的朋友。请阅读以下手记，然后针对其中提到的问题、困惑、想法或情绪，给出简短的评论和建议。

要求：
- 如果手记中有问题或困惑，提供有建设性的建议
- 如果手记中有想法或计划，给予鼓励和补充思考
- 如果手记中流露出情绪，提供适当的情绪支持
- 语气温暖、真诚，像朋友交流一样自然
- 控制在100-200字以内

手记内容：
{content[:1000]}

请直接给出你的评论，不要使用任何格式标记："""

    return await _call_local_only(prompt, "diary-comment")


def run_daily_diary_comment_sync():
    """Synchronous wrapper for APScheduler."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_daily_diary_comment())
        else:
            loop.run_until_complete(run_daily_diary_comment())
    except RuntimeError:
        asyncio.run(run_daily_diary_comment())
