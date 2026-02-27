import asyncio
import json
import logging
import time
import traceback
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models.talent import Talent, Tag, TalentTag, EntryLog, CardDimension
from app.middleware.auth_middleware import require_auth
from app.services.llm_service import update_talent_card, parse_pdf_content
from app.services.pdf_service import extract_text_from_pdf, pdf_to_images
from app.services.pinyin_service import get_pinyin_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/entry", tags=["entry"])


class TextEntryRequest(BaseModel):
    talent_id: int
    content: str


def _get_dimensions(db: Session) -> list[dict]:
    dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
    return [{"key": d.key, "label": d.label, "schema": d.schema} for d in dims]


def _apply_new_dimensions(db: Session, new_dimensions: list[dict]):
    """Add new dimensions suggested by LLM and update all existing talent cards."""
    if not new_dimensions:
        return

    for dim in new_dimensions:
        key = dim.get("key", "")
        if not key:
            continue

        existing = db.query(CardDimension).filter(CardDimension.key == key).first()
        if existing:
            continue

        max_order = db.query(CardDimension).count()
        new_dim = CardDimension(
            key=key,
            label=dim.get("label", key),
            schema=dim.get("schema", '""'),
            is_default=False,
            sort_order=max_order,
        )
        db.add(new_dim)
        db.flush()

        # Add this dimension to all existing talent cards with an empty default
        try:
            schema_val = json.loads(dim.get("schema", '""'))
        except (json.JSONDecodeError, TypeError):
            schema_val = ""

        # Derive proper empty default from schema type, not the schema itself
        if isinstance(schema_val, dict):
            schema_type = schema_val.get("type", "")
            if schema_type == "array" or isinstance(schema_val.get("items"), dict):
                default_value = []
            else:
                default_value = {}
        elif isinstance(schema_val, list):
            default_value = []
        else:
            default_value = ""

        all_talents = db.query(Talent).all()
        for talent in all_talents:
            card_data = talent.card_data or {}
            if key not in card_data:
                card_data[key] = default_value
                talent.card_data = card_data

        logger.info(f"New dimension added: {key} ({dim.get('label', key)})")


def _ensure_tags(db: Session, tag_names: list[str]) -> list[int]:
    """Ensure tags exist and return their IDs."""
    tag_ids = []
    for name in tag_names:
        name = name.strip()
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.flush()
        tag_ids.append(tag.id)
    return tag_ids


async def _process_text_entry_bg(entry_log_id: int, talent_id: int, content: str,
                                  existing_card_data: dict, dimensions: list[dict],
                                  talent_name: str):
    """Background task: call LLM and update talent card."""
    db = SessionLocal()
    try:
        result = await update_talent_card(
            user_input=content,
            existing_card_data=existing_card_data,
            dimensions=dimensions,
            talent_name=talent_name,
        )

        talent = db.query(Talent).filter(Talent.id == talent_id).first()
        if not talent:
            return

        # Apply new dimensions
        _apply_new_dimensions(db, result.get("new_dimensions", []))

        # Update talent card
        talent.card_data = result.get("card_data", talent.card_data)
        if result.get("summary"):
            talent.summary = result["summary"]

        # Handle suggested tags
        suggested_tags = result.get("suggested_tags", [])
        if suggested_tags:
            tag_ids = _ensure_tags(db, suggested_tags)
            existing_tag_ids = {tt.tag_id for tt in db.query(TalentTag).filter(
                TalentTag.talent_id == talent.id
            ).all()}
            for tid in tag_ids:
                if tid not in existing_tag_ids:
                    db.add(TalentTag(talent_id=talent.id, tag_id=tid))

        # Update entry log with LLM result and mark done
        entry_log = db.query(EntryLog).filter(EntryLog.id == entry_log_id).first()
        if entry_log:
            entry_log.llm_response = json.dumps(result, ensure_ascii=False)
            entry_log.status = "done"

        db.commit()
        logger.info(f"LLM processing done for talent {talent_id}, entry {entry_log_id}")

    except Exception as e:
        logger.error(f"Background LLM processing failed for entry {entry_log_id}: {e}\n{traceback.format_exc()}")
        try:
            entry_log = db.query(EntryLog).filter(EntryLog.id == entry_log_id).first()
            if entry_log:
                entry_log.status = "failed"
                entry_log.llm_response = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def _process_pdf_entry_bg(entry_log_id: int, talent_id: int,
                                 pdf_images: list[bytes], pdf_text_fallback: str,
                                 dimensions: list[dict], talent_name: str):
    """Background task: call VLM to parse PDF images and update talent card."""
    t_start = time.monotonic()
    db = SessionLocal()
    try:
        t0 = time.monotonic()
        result = await parse_pdf_content(
            pdf_images=pdf_images,
            dimensions=dimensions,
            talent_name=talent_name,
            pdf_text_fallback=pdf_text_fallback,
        )
        logger.info(f"[TIMING] PDF VLM parse: {time.monotonic() - t0:.1f}s (entry {entry_log_id})")

        # Ensure result is a dict
        if not isinstance(result, dict):
            logger.warning(f"parse_pdf_content returned non-dict: {type(result)}")
            result = {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": []}

        talent = db.query(Talent).filter(Talent.id == talent_id).first()
        if not talent:
            return

        # Apply new dimensions (validate each item is a dict)
        new_dims = result.get("new_dimensions", [])
        if isinstance(new_dims, list):
            new_dims = [d for d in new_dims if isinstance(d, dict)]
            _apply_new_dimensions(db, new_dims)

        # Update talent basic info from extraction
        extracted = result.get("extracted_info", {})
        if not isinstance(extracted, dict):
            extracted = {}
        if extracted.get("email") and not talent.email:
            talent.email = extracted["email"]
        if extracted.get("phone") and not talent.phone:
            talent.phone = extracted["phone"]
        if extracted.get("current_role") and not talent.current_role:
            talent.current_role = extracted["current_role"]
        if extracted.get("department") and not talent.department:
            talent.department = extracted["department"]

        # Merge card data
        new_card_data = result.get("card_data", {})
        if isinstance(new_card_data, dict):
            existing_card = talent.card_data or {}
            for key, value in new_card_data.items():
                if value and value != "" and value != [] and value != {}:
                    existing_card[key] = value
            talent.card_data = existing_card

        if result.get("summary"):
            talent.summary = result["summary"]

        # Handle tags
        suggested_tags = result.get("suggested_tags", [])
        if isinstance(suggested_tags, list) and suggested_tags:
            tag_ids = _ensure_tags(db, [t for t in suggested_tags if isinstance(t, str)])
            existing_tag_ids = {tt.tag_id for tt in db.query(TalentTag).filter(
                TalentTag.talent_id == talent.id
            ).all()}
            for tid in tag_ids:
                if tid not in existing_tag_ids:
                    db.add(TalentTag(talent_id=talent.id, tag_id=tid))

        # Update entry log
        entry_log = db.query(EntryLog).filter(EntryLog.id == entry_log_id).first()
        if entry_log:
            entry_log.llm_response = json.dumps(result, ensure_ascii=False)
            entry_log.status = "done"

        t1 = time.monotonic()
        db.commit()
        logger.info(f"PDF LLM processing done for talent {talent_id}, entry {entry_log_id}, total: {t1 - t_start:.1f}s")

    except Exception as e:
        logger.error(f"Background PDF processing failed for entry {entry_log_id}: {e}\n{traceback.format_exc()}")
        try:
            entry_log = db.query(EntryLog).filter(EntryLog.id == entry_log_id).first()
            if entry_log:
                entry_log.status = "failed"
                entry_log.llm_response = json.dumps({"error": str(e)}, ensure_ascii=False)
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/text")
async def submit_text_entry(
    body: TextEntryRequest,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Submit text information. Saves immediately, LLM processes in background."""
    talent = db.query(Talent).filter(Talent.id == body.talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    dimensions = _get_dimensions(db)

    # Save entry log immediately with "processing" status
    entry_log = EntryLog(
        talent_id=talent.id,
        content=body.content,
        source="manual",
        status="processing",
    )
    db.add(entry_log)
    db.commit()
    db.refresh(entry_log)

    # Fire LLM processing in background
    asyncio.create_task(_process_text_entry_bg(
        entry_log_id=entry_log.id,
        talent_id=talent.id,
        content=body.content,
        existing_card_data=talent.card_data or {},
        dimensions=dimensions,
        talent_name=talent.name,
    ))

    return {
        "message": "信息已接收，后台整理中",
        "entry_id": entry_log.id,
        "talent_id": talent.id,
        "status": "processing",
    }


@router.post("/pdf")
async def upload_pdf_resume(
    talent_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Upload a PDF resume. Saves immediately, LLM processes in background."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传PDF文件")

    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    # Read PDF bytes
    pdf_bytes = await file.read()

    # Convert PDF pages to images for VLM
    t0 = time.monotonic()
    try:
        pdf_images = pdf_to_images(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF to image conversion failed: {e}")
        raise HTTPException(status_code=400, detail="PDF解析失败，请确保文件有效")
    logger.info(f"[TIMING] pdf_to_images ({len(pdf_images)} pages): {time.monotonic() - t0:.2f}s")

    if not pdf_images:
        raise HTTPException(status_code=400, detail="PDF中未识别到任何页面")

    # Also try text extraction as supplementary context (best-effort)
    t1 = time.monotonic()
    pdf_text_fallback = ""
    try:
        pdf_text_fallback = extract_text_from_pdf(pdf_bytes)
    except Exception:
        pass
    logger.info(f"[TIMING] pdfplumber text extract: {time.monotonic() - t1:.2f}s")

    dimensions = _get_dimensions(db)

    # Save entry log immediately
    entry_log = EntryLog(
        talent_id=talent.id,
        content=f"[PDF上传] {file.filename} ({len(pdf_images)}页)",
        source="pdf",
        status="processing",
    )
    db.add(entry_log)
    db.commit()
    db.refresh(entry_log)

    # Fire VLM processing in background
    asyncio.create_task(_process_pdf_entry_bg(
        entry_log_id=entry_log.id,
        talent_id=talent.id,
        pdf_images=pdf_images,
        pdf_text_fallback=pdf_text_fallback,
        dimensions=dimensions,
        talent_name=talent.name,
    ))

    return {
        "message": "简历已上传，后台解析中",
        "entry_id": entry_log.id,
        "talent_id": talent.id,
        "status": "processing",
    }


@router.get("/status/{entry_id}")
async def get_entry_status(
    entry_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Check the processing status of an entry."""
    entry = db.query(EntryLog).filter(EntryLog.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")

    return {
        "entry_id": entry.id,
        "status": entry.status or "done",
        "talent_id": entry.talent_id,
    }


@router.delete("/logs/{entry_id}")
async def delete_entry_log(
    entry_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Delete a single entry log."""
    entry = db.query(EntryLog).filter(EntryLog.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(entry)
    db.commit()
    return {"message": "已删除"}


@router.get("/logs/{talent_id}")
async def get_entry_logs(
    talent_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Get entry history for a talent."""
    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    logs = db.query(EntryLog).filter(
        EntryLog.talent_id == talent_id
    ).order_by(EntryLog.created_at.desc()).all()

    return [
        {
            "id": log.id,
            "content": log.content,
            "source": log.source,
            "status": log.status or "done",
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in logs
    ]
