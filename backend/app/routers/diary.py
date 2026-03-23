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
        "comment_feedback": entry.comment_feedback,
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


# ---- Comment feedback (like / dislike) ----

@router.post("/entries/{entry_id}/comment-feedback")
def set_comment_feedback(
    entry_id: int,
    body: dict,
    db: Session = Depends(get_db),
    _: bool = Depends(_verify_diary_password),
):
    """Set feedback on an AI comment: 'liked', 'disliked', or null to clear."""
    entry = db.query(DiaryEntry).filter(DiaryEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="手记不存在")
    feedback = body.get("feedback")  # "liked" / "disliked" / null
    if feedback not in ("liked", "disliked", None):
        raise HTTPException(status_code=400, detail="feedback must be 'liked', 'disliked', or null")
    entry.comment_feedback = feedback
    db.commit()
    return {"ok": True, "comment_feedback": feedback}


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
    """Run by scheduler. Generates AI comments for uncommented entries and re-generates disliked ones."""
    db = SessionLocal()
    try:
        today = date.today().isoformat()

        # 1. Entries without any comment yet (today)
        new_entries = db.query(DiaryEntry).filter(
            DiaryEntry.diary_date == today,
            DiaryEntry.llm_comment.is_(None),
        ).all()

        # 2. Entries whose comment was disliked (any date) — regenerate
        disliked_entries = db.query(DiaryEntry).filter(
            DiaryEntry.comment_feedback == "disliked",
        ).all()

        all_entries = {e.id: e for e in new_entries}
        for e in disliked_entries:
            all_entries[e.id] = e

        if not all_entries:
            logger.info("Diary comment: nothing to process")
            return

        # Collect liked examples as few-shot samples
        liked_examples = _get_liked_examples(db)

        logger.info(f"Diary comment: processing {len(all_entries)} entries ({len(new_entries)} new, {len(disliked_entries)} disliked)")
        for entry in all_entries.values():
            comment = await _generate_diary_comment(entry.content, liked_examples)
            if comment:
                entry.llm_comment = comment
                entry.comment_feedback = None  # reset feedback after regeneration
                entry.commented_at = datetime.utcnow()
                db.commit()
                logger.info(f"Diary comment: generated for entry {entry.id}")
    except Exception as e:
        logger.error(f"Diary daily comment job failed: {e}")
    finally:
        db.close()


def _get_liked_examples(db, limit: int = 3) -> list[dict]:
    """Fetch recent liked comment examples to use as few-shot prompt."""
    liked = (
        db.query(DiaryEntry)
        .filter(DiaryEntry.comment_feedback == "liked", DiaryEntry.llm_comment.isnot(None))
        .order_by(DiaryEntry.commented_at.desc())
        .limit(limit)
        .all()
    )
    return [{"content": e.content[:300], "comment": e.llm_comment} for e in liked]


DEFAULT_DIARY_COMMENT_PROMPT = """你是一位阅历丰富、思维敏锐的朋友。请阅读以下手记，给出你的真实想法。

要求：
- 说人话，不要鸡汤、不要空洞的鼓励，不要"加油"之类的废话
- 如果手记提到了具体问题或困惑，直接给出你的分析和可操作的建议
- 如果手记记录了一个想法，指出你觉得有意思的点，也可以指出潜在的盲区
- 如果手记是情绪表达，简短回应即可，不要过度共情或说教
- 有自己的观点，可以提出不同看法，但要言之有理
- 控制在100-200字以内，言简意赅"""


def _get_diary_comment_instructions() -> str:
    from app.config import get_instruction
    return get_instruction("diary_comment", DEFAULT_DIARY_COMMENT_PROMPT)


@router.get("/comment-prompt")
def get_comment_prompt(db: Session = Depends(get_db), _: bool = Depends(_verify_diary_password)):
    """Get the current diary comment prompt template + liked/disliked stats."""
    liked_examples = _get_liked_examples(db)
    disliked_count = db.query(DiaryEntry).filter(DiaryEntry.comment_feedback == "disliked").count()
    return {
        "instructions": _get_diary_comment_instructions(),
        "default": DEFAULT_DIARY_COMMENT_PROMPT,
        "liked_examples": liked_examples,
        "disliked_count": disliked_count,
    }


@router.put("/comment-prompt")
def save_comment_prompt(body: dict, _: bool = Depends(_verify_diary_password)):
    """Save custom diary comment prompt template."""
    from app.config import save_instruction
    instructions = body.get("instructions", "").strip()
    save_instruction("diary_comment", instructions)
    return {"ok": True}


async def _generate_diary_comment(content: str, liked_examples: list[dict] | None = None) -> str | None:
    """Generate a thoughtful, substantive AI comment for a diary entry."""

    base_prompt = _get_diary_comment_instructions()

    # Build few-shot section from liked examples
    examples_section = ""
    if liked_examples:
        examples_section = "\n\n以下是几个被认可的优秀评论范例，请参考这种风格和深度：\n"
        for i, ex in enumerate(liked_examples, 1):
            examples_section += f"\n范例{i}：\n手记：{ex['content']}\n评论：{ex['comment']}\n"

    prompt = f"""{base_prompt}{examples_section}

手记内容：
{content[:1000]}

请直接给出你的评论："""

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
