import json
import logging
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


def _talent_to_response(talent: Talent) -> dict:
    return {
        "id": talent.id,
        "name": talent.name,
        "name_pinyin": talent.name_pinyin or "",
        "email": talent.email or "",
        "phone": talent.phone or "",
        "current_role": talent.current_role or "",
        "department": talent.department or "",
        "card_data": talent.card_data or {},
        "summary": talent.summary or "",
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
    return [{"id": t.id, "name": t.name, "color": t.color} for t in tags]


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
