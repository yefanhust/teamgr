import json
import logging
import re
from datetime import date, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.talent import Talent, Tag, TalentTag, CardDimension
from app.middleware.auth_middleware import require_auth
from app.services.pinyin_service import get_pinyin_data, match_pinyin
from app.services.pdf_service import generate_talent_card_pdf
from app.services.llm_service import semantic_search

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/talents", tags=["talents"])


class TalentCreate(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    current_role: str = ""
    department: str = ""


class TalentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    current_role: Optional[str] = None
    department: Optional[str] = None
    status: Optional[str] = None
    tag_ids: Optional[list[int]] = None
    card_data: Optional[dict] = None


class TalentResponse(BaseModel):
    id: int
    name: str
    name_pinyin: str
    email: str
    phone: str
    current_role: str
    department: str
    card_data: dict
    summary: str
    tags: list[dict]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TagCreate(BaseModel):
    name: str
    color: str = "#3B82F6"


def _compute_age_from_birthday(birthday_str: str) -> str:
    """Compute age from birthday string, precise to 2 decimal places.

    Supports formats: YYYY-MM-DD, YYYY-MM, YYYY.
    """
    if not birthday_str:
        return ""
    try:
        s = birthday_str.strip()
        # Try YYYY-MM-DD
        if re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', s):
            bday = datetime.strptime(s, "%Y-%m-%d").date()
        # Try YYYY-MM
        elif re.match(r'^\d{4}-\d{1,2}$', s):
            bday = datetime.strptime(s, "%Y-%m").date()  # defaults to 1st
        # Try YYYY only
        elif re.match(r'^\d{4}$', s):
            bday = date(int(s), 1, 1)
        else:
            return ""
        today = date.today()
        delta_days = (today - bday).days
        age = delta_days / 365.25
        return f"{age:.2f}"
    except (ValueError, TypeError):
        return ""


def _build_summary(name: str, age: str, raw_summary: str) -> str:
    """Rebuild summary to start with '姓名，xx岁，' using computed age."""
    if not raw_summary:
        if age:
            return f"{name}，{age}岁"
        return name
    s = raw_summary
    # Strip existing name prefix
    if s.startswith(name):
        s = s[len(name):]
        s = s.lstrip("，, ")
    # Strip existing age patterns like "男，29.67岁，" or "27岁，" or "29.67（1996-07-01）岁，"
    s = re.sub(r'^[男女][\s，,]*', '', s)
    s = re.sub(r'^\d+[\.\d]*(?:（[^）]*）)?岁[\s，,]*', '', s)
    if age:
        return f"{name}，{age}岁，{s}" if s else f"{name}，{age}岁"
    return f"{name}，{s}" if s else name


def _compute_status(talent: Talent) -> str:
    """Compute talent status: manual status takes priority, otherwise derive from interview feedback."""
    manual_status = getattr(talent, "status", "") or ""
    if manual_status:
        return manual_status
    # Auto-derive from interview_feedback
    card_data = talent.card_data or {}
    feedbacks = card_data.get("interview_feedback")
    if isinstance(feedbacks, list) and feedbacks:
        latest = feedbacks[-1]
        if isinstance(latest, dict):
            result = latest.get("result", "")
            if result == "通过":
                return "面试通过"
            elif result == "否决":
                return "面试否决"
    return ""


def _talent_to_response(talent: Talent) -> dict:
    card_data = talent.card_data or {}
    pi = card_data.get("personal_info")
    computed_age = ""
    if isinstance(pi, dict) and pi.get("birthday"):
        computed_age = _compute_age_from_birthday(pi["birthday"])
        if computed_age:
            pi = {**pi, "age": computed_age}
            card_data = {**card_data, "personal_info": pi}
    summary = _build_summary(talent.name, computed_age, talent.summary or "")
    return {
        "id": talent.id,
        "name": talent.name,
        "name_pinyin": talent.name_pinyin or "",
        "name_pinyin_initials": talent.name_pinyin_initials or "",
        "email": talent.email or "",
        "phone": talent.phone or "",
        "current_role": talent.current_role or "",
        "department": talent.department or "",
        "status": _compute_status(talent),
        "card_data": card_data,
        "summary": summary,
        "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in talent.tags],
        "created_at": talent.created_at.isoformat() if talent.created_at else "",
        "updated_at": talent.updated_at.isoformat() if talent.updated_at else "",
    }


@router.get("")
async def list_talents(
    tag_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    query = db.query(Talent)
    if tag_id:
        query = query.join(TalentTag).filter(TalentTag.tag_id == tag_id)

    total = query.count()
    talents = query.order_by(Talent.updated_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_talent_to_response(t) for t in talents],
    }


@router.get("/search")
async def search_talents(
    q: str = Query("", min_length=0),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Search talents by name (supports pinyin fuzzy matching)."""
    if not q.strip():
        talents = db.query(Talent).order_by(Talent.name).limit(50).all()
        return [_talent_to_response(t) for t in talents]

    all_talents = db.query(Talent).all()
    matched = [
        t for t in all_talents
        if match_pinyin(q, t.name, t.name_pinyin or "", t.name_pinyin_initials or "")
    ]

    return [_talent_to_response(t) for t in matched]


@router.post("/semantic-search")
async def semantic_search_talents(
    body: dict,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """LLM-powered semantic search."""
    query = body.get("query", "")
    if not query.strip():
        return []

    all_talents = db.query(Talent).all()
    summaries = [
        {
            "id": t.id,
            "name": t.name,
            "summary": t.summary or "",
            "tags": [tag.name for tag in t.tags],
        }
        for t in all_talents
    ]

    matched_ids = await semantic_search(query, summaries)

    id_to_talent = {t.id: t for t in all_talents}
    results = []
    for tid in matched_ids:
        if tid in id_to_talent:
            results.append(_talent_to_response(id_to_talent[tid]))

    return results


@router.get("/dimensions")
async def get_dimensions(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Get all card dimensions."""
    dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
    return [
        {
            "id": d.id,
            "key": d.key,
            "label": d.label,
            "schema": d.schema,
            "is_default": d.is_default,
            "sort_order": d.sort_order,
        }
        for d in dims
    ]


@router.get("/{talent_id}")
async def get_talent(
    talent_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")
    return _talent_to_response(talent)


@router.post("")
async def create_talent(
    body: TalentCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    # Check name uniqueness
    existing = db.query(Talent).filter(Talent.name == body.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"已存在同名人才「{body.name}」")

    pinyin_full, pinyin_initials = get_pinyin_data(body.name)

    # Build initial card_data from dimensions
    dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
    card_data = {}
    for dim in dims:
        try:
            card_data[dim.key] = json.loads(dim.schema)
        except (json.JSONDecodeError, TypeError):
            card_data[dim.key] = ""

    talent = Talent(
        name=body.name,
        name_pinyin=pinyin_full,
        name_pinyin_initials=pinyin_initials,
        email=body.email,
        phone=body.phone,
        current_role=body.current_role,
        department=body.department,
        card_data=card_data,
    )
    db.add(talent)
    db.commit()
    db.refresh(talent)
    return _talent_to_response(talent)


@router.put("/{talent_id}")
async def update_talent(
    talent_id: int,
    body: TalentUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    if body.name is not None:
        # Check name uniqueness (exclude self)
        dup = db.query(Talent).filter(
            Talent.name == body.name.strip(), Talent.id != talent_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"已存在同名人才「{body.name}」")
        talent.name = body.name
        pinyin_full, pinyin_initials = get_pinyin_data(body.name)
        talent.name_pinyin = pinyin_full
        talent.name_pinyin_initials = pinyin_initials
    if body.email is not None:
        talent.email = body.email
    if body.phone is not None:
        talent.phone = body.phone
    if body.current_role is not None:
        talent.current_role = body.current_role
    if body.department is not None:
        talent.department = body.department
    if body.status is not None:
        talent.status = body.status

    if body.card_data is not None:
        # Merge provided card_data into existing
        existing = dict(talent.card_data or {})
        existing.update(body.card_data)
        talent.card_data = existing

    if body.tag_ids is not None:
        # Clear existing tags and set new ones
        db.query(TalentTag).filter(TalentTag.talent_id == talent_id).delete()
        for tag_id in body.tag_ids:
            db.add(TalentTag(talent_id=talent_id, tag_id=tag_id))

    db.commit()
    db.refresh(talent)
    return _talent_to_response(talent)


@router.delete("/{talent_id}")
async def delete_talent(
    talent_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")
    db.delete(talent)
    db.commit()
    return {"message": "已删除"}


@router.get("/{talent_id}/export-pdf")
async def export_talent_pdf(
    talent_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
    dimensions = [{"key": d.key, "label": d.label, "schema": d.schema} for d in dims]

    talent_data = {
        "name": talent.name,
        "email": talent.email,
        "phone": talent.phone,
        "current_role": talent.current_role,
        "department": talent.department,
        "card_data": talent.card_data or {},
        "summary": talent.summary or "",
        "tags": [t.name for t in talent.tags],
    }

    pdf_bytes = generate_talent_card_pdf(talent_data, dimensions)

    from urllib.parse import quote
    filename = f"talent_{talent.name}.pdf"
    encoded = quote(filename)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"
        },
    )


# --- Tag endpoints ---

@router.get("/tags/all")
async def list_tags(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    tags = db.query(Tag).order_by(Tag.name).all()
    return [
        {"id": t.id, "name": t.name, "color": t.color, "parent_id": t.parent_id}
        for t in tags
    ]


@router.post("/tags")
async def create_tag(
    body: TagCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    existing = db.query(Tag).filter(Tag.name == body.name).first()
    if existing:
        return {"id": existing.id, "name": existing.name, "color": existing.color}

    tag = Tag(name=body.name, color=body.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.get("/tags/organize-prompt")
async def get_organize_prompt(_=Depends(require_auth)):
    """Get the current organize prompt instructions."""
    return {"instructions": _get_organize_instructions(), "default": DEFAULT_ORGANIZE_INSTRUCTIONS}


@router.put("/tags/organize-prompt")
async def save_organize_prompt_endpoint(body: dict, _=Depends(require_auth)):
    """Save custom organize prompt instructions."""
    from app.config import save_instruction
    instructions = body.get("instructions", "").strip()
    save_instruction("talent_organize_tags", instructions)
    return {"ok": True}


@router.put("/tags/{tag_id}")
async def update_tag(
    tag_id: int,
    body: TagCreate,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Update a tag's name and/or color."""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if body.name and body.name != tag.name:
        dup = db.query(Tag).filter(Tag.name == body.name, Tag.id != tag_id).first()
        if dup:
            raise HTTPException(status_code=400, detail="标签名已存在")
        tag.name = body.name
    if body.color:
        tag.color = body.color
    db.commit()
    db.refresh(tag)
    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Delete a tag and remove it from all talents."""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.query(TalentTag).filter(TalentTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()
    return {"message": "已删除"}


DEFAULT_ORGANIZE_INSTRUCTIONS = """你是一个标签分类专家。请完成以下两个任务：

## 任务1：合并同义标签
找出语义相同或高度相似的标签组，选择最简洁准确的一个作为保留名，其余作为待合并项。
判断标准：含义本质相同只是措辞不同（如"紧急联系人已登记"和"紧急联系人已备案"）。
注意：含义不同的标签不要合并（如"Python"和"Java"虽然都是编程语言但不应合并）。

## 任务2：分层归类
将合并后的标签归类为一级标签（大分类）和二级标签（具体标签）的层级结构。
要求：
1. 一级标签是新创建的大分类名称（如"技术方向"、"学历背景"、"个人特质"等），数量控制在3-8个
2. 每个保留的标签都必须归入某个一级标签下作为二级标签
3. 一级标签名称要简洁、有概括性
4. 所有保留的标签都必须被分配，不能遗漏""".strip()


def _get_organize_instructions() -> str:
    from app.config import get_instruction
    return get_instruction("talent_organize_tags", DEFAULT_ORGANIZE_INSTRUCTIONS)


def _build_organize_prompt(tag_names: list[str]) -> str:
    instructions = _get_organize_instructions()
    return f"""{instructions}

现有标签列表：
{json.dumps(tag_names, ensure_ascii=False)}

请严格按以下JSON格式返回，不要包含其他内容：
{{
  "deletes": ["需要删除的标签1", "需要删除的标签2"],
  "renames": [
    {{"from": "原标签名", "to": "新标签名"}}
  ],
  "merges": [
    {{"keep": "保留的标签名", "remove": ["待合并标签1", "待合并标签2"]}}
  ],
  "categories": [
    {{
      "name": "一级标签名称",
      "color": "#十六进制颜色",
      "children": ["二级标签1", "二级标签2"]
    }}
  ]
}}

如果没有需要删除的标签，deletes 返回空数组 []。
如果没有需要重命名的标签，renames 返回空数组 []。
如果没有需要合并的标签，merges 返回空数组 []。"""


def _rename_tags(db: Session, renames: list[dict]) -> list[str]:
    """Rename tags. Returns list of human-readable descriptions."""
    descriptions = []
    for r in renames:
        old_name = r.get("from", "")
        new_name = r.get("to", "")
        if not old_name or not new_name or old_name == new_name:
            continue
        tag = db.query(Tag).filter(Tag.name == old_name).first()
        if not tag:
            continue
        existing = db.query(Tag).filter(Tag.name == new_name).first()
        if existing:
            continue  # skip if target name already exists
        tag.name = new_name
        descriptions.append(f"{old_name} → {new_name}")
    if descriptions:
        db.flush()
    return descriptions


def _delete_tags(db: Session, delete_names: list[str]) -> list[str]:
    """Delete specified tags and their associations. Returns list of deleted tag names."""
    deleted = []
    for name in delete_names:
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            continue
        db.query(TalentTag).filter(TalentTag.tag_id == tag.id).delete()
        db.delete(tag)
        deleted.append(name)
    if deleted:
        db.flush()
    return deleted


def _merge_similar_tags(db: Session, merges: list[dict]) -> list[str]:
    """Merge similar tags: reassign talent associations then delete duplicates.
    Returns list of human-readable merge descriptions.
    """
    descriptions = []
    for merge in merges:
        keep_name = merge.get("keep", "")
        remove_names = merge.get("remove", [])
        if not keep_name or not remove_names:
            continue

        keep_tag = db.query(Tag).filter(Tag.name == keep_name).first()
        if not keep_tag:
            continue

        for rm_name in remove_names:
            rm_tag = db.query(Tag).filter(Tag.name == rm_name).first()
            if not rm_tag or rm_tag.id == keep_tag.id:
                continue

            # Reassign talent associations: move from rm_tag to keep_tag
            existing_talent_ids = {
                row.talent_id for row in
                db.query(TalentTag).filter(TalentTag.tag_id == keep_tag.id).all()
            }
            for link in db.query(TalentTag).filter(TalentTag.tag_id == rm_tag.id).all():
                if link.talent_id not in existing_talent_ids:
                    link.tag_id = keep_tag.id
                else:
                    db.delete(link)
            db.flush()

            # Delete the duplicate tag
            db.delete(rm_tag)

        descriptions.append(f"{', '.join(remove_names)} → {keep_name}")

    if descriptions:
        db.flush()
    return descriptions


def _apply_tag_hierarchy(db: Session, categories: list[dict]):
    """Apply LLM-generated hierarchy to database tags."""
    db.expire_all()  # ensure fresh data after deletes/renames/merges
    tags = db.query(Tag).all()
    tag_map = {t.name: t for t in tags}

    # Reset all parent_id first so stale hierarchy is cleared
    for t in tags:
        t.parent_id = None
    db.flush()

    for cat in categories:
        parent_name = cat["name"]
        parent_color = cat.get("color", "#6B7280")
        children_names = cat.get("children", [])

        parent_tag = tag_map.get(parent_name)
        if not parent_tag:
            parent_tag = db.query(Tag).filter(Tag.name == parent_name).first()
        if not parent_tag:
            parent_tag = Tag(name=parent_name, color=parent_color, parent_id=None)
            db.add(parent_tag)
            db.flush()
        else:
            parent_tag.parent_id = None
            parent_tag.color = parent_color

        for child_name in children_names:
            child_tag = tag_map.get(child_name)
            if child_tag and child_tag.id != parent_tag.id:
                child_tag.parent_id = parent_tag.id
                child_tag.color = "#3B82F6"
            elif not child_tag:
                logger.warning(f"Tag organize: '{child_name}' in category '{parent_name}' not found in DB, skipping")

    db.flush()

    # Fallback: assign uncategorized tags (with talent links) to "未分类"
    all_tags = db.query(Tag).all()
    parent_ids = {t.parent_id for t in all_tags if t.parent_id}
    orphans = [t for t in all_tags if t.parent_id is None and t.id not in parent_ids and len(t.talents) > 0]
    if orphans:
        logger.warning(f"Tag organize: {len(orphans)} tags uncategorized, assigning to '未分类': {[t.name for t in orphans]}")
        fallback = db.query(Tag).filter(Tag.name == "未分类").first()
        if not fallback:
            fallback = Tag(name="未分类", color="#9CA3AF", parent_id=None)
            db.add(fallback)
            db.flush()
        for t in orphans:
            t.parent_id = fallback.id
        db.flush()

    # Clean up orphan tags: no parent, no children, no talent links
    all_tags = db.query(Tag).all()
    parent_ids = {t.parent_id for t in all_tags if t.parent_id}
    for t in all_tags:
        if t.parent_id is None and t.id not in parent_ids and len(t.talents) == 0:
            db.delete(t)

    db.commit()



@router.post("/tags/organize")
async def organize_tags(
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Use LLM to organize tags with SSE streaming."""
    import asyncio
    import time
    from app.services.llm_service import _record_llm_usage

    tags = db.query(Tag).all()
    if not tags:
        raise HTTPException(status_code=400, detail="没有标签需要整理")

    tag_names = [t.name for t in tags]
    prompt = _build_organize_prompt(tag_names)

    async def event_stream():
        import threading
        full_text = ""
        usage = None
        t0 = time.monotonic()
        try:
            from google import genai
            from google.genai import types as genai_types
            from app.config import get_gemini_config, get_model_defaults
            from app.services.llm_service import get_current_model_name

            cfg = get_gemini_config()
            api_key = cfg.get("api_key", "")
            if not api_key or api_key == "your-gemini-api-key-here":
                yield f"data: {json.dumps({'type': 'error', 'content': 'LLM模型不可用'}, ensure_ascii=False)}\n\n"
                return

            organize_model = get_model_defaults().get("organize-tags") or get_current_model_name()
            client = genai.Client(api_key=api_key)

            # Use queue + thread to avoid blocking the event loop
            queue = asyncio.Queue()
            loop = asyncio.get_event_loop()
            stream_error = [None]

            def produce():
                try:
                    response = client.models.generate_content_stream(
                        model=organize_model,
                        contents=prompt,
                        config=genai_types.GenerateContentConfig(
                            thinking_config=genai_types.ThinkingConfig(
                                include_thoughts=True,
                            ),
                        ),
                    )
                    last_usage = None
                    for chunk in response:
                        parts = []
                        try:
                            for part in chunk.candidates[0].content.parts:
                                is_thought = getattr(part, 'thought', False)
                                text = getattr(part, 'text', '') or ''
                                if text:
                                    parts.append(('thought' if is_thought else 'text', text))
                        except (IndexError, AttributeError):
                            pass
                        if parts:
                            loop.call_soon_threadsafe(queue.put_nowait, ('_parts', parts))
                        last_usage = getattr(chunk, 'usage_metadata', None) or last_usage
                    loop.call_soon_threadsafe(queue.put_nowait, ('_meta', last_usage))
                except Exception as e:
                    stream_error[0] = e
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=produce, daemon=True).start()

            in_thinking = False
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    # No chunk yet — send heartbeat so frontend knows we're still working
                    elapsed = int(time.monotonic() - t0)
                    yield f"data: {json.dumps({'type': 'thinking', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
                    continue
                if item is None:
                    break
                if isinstance(item, tuple) and item[0] == '_meta':
                    usage = item[1]
                    continue
                if isinstance(item, tuple) and item[0] == '_parts':
                    for kind, text in item[1]:
                        if kind == 'thought':
                            if not in_thinking:
                                in_thinking = True
                            yield f"data: {json.dumps({'type': 'thinking_chunk', 'content': text}, ensure_ascii=False)}\n\n"
                        else:
                            if in_thinking:
                                in_thinking = False
                                elapsed = int(time.monotonic() - t0)
                                yield f"data: {json.dumps({'type': 'thinking_done', 'elapsed': elapsed}, ensure_ascii=False)}\n\n"
                            full_text += text
                            yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"

            if stream_error[0]:
                raise stream_error[0]

            duration_ms = int((time.monotonic() - t0) * 1000)
            isl = getattr(usage, 'prompt_token_count', 0) or getattr(usage, 'input_tokens', 0) if usage else 0
            osl = getattr(usage, 'candidates_token_count', 0) or getattr(usage, 'output_tokens', 0) if usage else 0
            _record_llm_usage(organize_model, "organize-tags", duration_ms, isl, osl)

            # Parse result
            text = full_text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```\w*\n?', '', text)
                text = re.sub(r'\n?```$', '', text)
            result = json.loads(text)

            # Step 1: Delete tags
            deletes = result.get("deletes", [])
            if deletes:
                deleted = _delete_tags(db, deletes)
                if deleted:
                    yield f"data: {json.dumps({'type': 'delete', 'deleted': deleted}, ensure_ascii=False)}\n\n"

            # Step 2: Rename tags
            renames = result.get("renames", [])
            if renames:
                rename_descs = _rename_tags(db, renames)
                if rename_descs:
                    yield f"data: {json.dumps({'type': 'rename', 'renames': rename_descs}, ensure_ascii=False)}\n\n"

            # Step 3: Merge similar tags
            merges = result.get("merges", [])
            if merges:
                merge_descs = _merge_similar_tags(db, merges)
                if merge_descs:
                    yield f"data: {json.dumps({'type': 'merge', 'merges': merge_descs}, ensure_ascii=False)}\n\n"

            # Step 4: Apply hierarchy
            categories = result.get("categories", [])
            if not categories:
                yield f"data: {json.dumps({'type': 'error', 'content': '未返回分类结果'}, ensure_ascii=False)}\n\n"
                return

            _apply_tag_hierarchy(db, categories)

            # Return final tag list
            all_tags = db.query(Tag).order_by(Tag.name).all()
            tag_list = [
                {"id": t.id, "name": t.name, "color": t.color, "parent_id": t.parent_id}
                for t in all_tags
            ]
            yield f"data: {json.dumps({'type': 'done', 'tags': tag_list}, ensure_ascii=False)}\n\n"

        except json.JSONDecodeError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'LLM返回格式错误'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Tag organize error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def run_daily_tag_organize():
    """Background job: run talent tag organize (non-streaming)."""
    import time
    from app.database import SessionLocal
    from app.services.llm_service import _record_llm_usage

    db = SessionLocal()
    try:
        tags = db.query(Tag).all()
        if not tags:
            logger.info("Daily tag organize: no tags, skipping")
            return

        tag_names = [t.name for t in tags]
        prompt = _build_organize_prompt(tag_names)

        from google import genai
        from google.genai import types as genai_types
        from app.config import get_gemini_config, get_model_defaults
        from app.services.llm_service import get_current_model_name

        cfg = get_gemini_config()
        api_key = cfg.get("api_key", "")
        if not api_key or api_key == "your-gemini-api-key-here":
            logger.warning("Daily tag organize: Gemini API key not configured, skipping")
            return

        organize_model = get_model_defaults().get("organize-tags") or get_current_model_name()
        client = genai.Client(api_key=api_key)

        t0 = time.monotonic()
        response = client.models.generate_content(
            model=organize_model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(include_thoughts=True),
            ),
        )

        full_text = ""
        for part in response.candidates[0].content.parts:
            if not getattr(part, 'thought', False):
                full_text += getattr(part, 'text', '') or ''

        duration_ms = int((time.monotonic() - t0) * 1000)
        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) if usage else 0
        osl = getattr(usage, 'candidates_token_count', 0) if usage else 0
        _record_llm_usage(organize_model, "organize-tags", duration_ms, isl, osl)

        text = full_text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```\w*\n?', '', text)
            text = re.sub(r'\n?```$', '', text)
        result = json.loads(text)

        deletes = result.get("deletes", [])
        if deletes:
            deleted = _delete_tags(db, deletes)
            logger.info(f"Daily tag organize: deleted {len(deleted)} tags")

        renames = result.get("renames", [])
        if renames:
            rename_descs = _rename_tags(db, renames)
            logger.info(f"Daily tag organize: renamed {len(rename_descs)} tags")

        merges = result.get("merges", [])
        if merges:
            merge_descs = _merge_similar_tags(db, merges)
            logger.info(f"Daily tag organize: merged {len(merge_descs)} groups")

        categories = result.get("categories", [])
        if categories:
            _apply_tag_hierarchy(db, categories)
            logger.info(f"Daily tag organize: applied {len(categories)} categories")
        else:
            logger.warning("Daily tag organize: LLM returned no categories")

        logger.info("Daily tag organize completed successfully")

    except Exception as e:
        logger.error(f"Daily tag organize failed: {e}")
    finally:
        db.close()


def check_missed_tag_organize(scheduler):
    """On startup, check if yesterday's tag organize was missed and schedule recovery."""
    from datetime import datetime, timedelta
    from app.database import SessionLocal
    from app.models.talent import LLMUsageLog
    from app.config import get_scheduler_config

    if scheduler is None:
        return

    sc = get_scheduler_config().get("daily_tag_organize", {})
    cron_hour = sc.get("cron_hour", 22)
    cron_minute = sc.get("cron_minute", 0)

    now = datetime.now()
    yesterday = now - timedelta(days=1)

    # Check if organize-tags ran yesterday (after the scheduled time)
    scheduled_yesterday = yesterday.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)

    db = SessionLocal()
    try:
        last_run = (
            db.query(LLMUsageLog)
            .filter(
                LLMUsageLog.call_type == "organize-tags",
                LLMUsageLog.timestamp >= scheduled_yesterday,
            )
            .first()
        )
        if last_run:
            return  # Already ran

        # Also skip if today's scheduled time hasn't passed yet AND we're before that time
        scheduled_today = now.replace(hour=cron_hour, minute=cron_minute, second=0, microsecond=0)
        if now < scheduled_today and (now - yesterday.replace(hour=0, minute=0)).days < 1:
            # Only recover if yesterday's scheduled time has truly passed
            pass  # fall through to schedule recovery

        delay_seconds = 90
        run_at = datetime.now() + timedelta(seconds=delay_seconds)
        scheduler.add_job(
            run_daily_tag_organize,
            "date",
            run_date=run_at,
            id="tag_organize_recovery",
        )
        logger.info(f"Tag organize: missed execution detected, recovery scheduled in {delay_seconds}s")
    except Exception as e:
        logger.warning(f"Tag organize missed execution check failed: {e}")
    finally:
        db.close()
