import asyncio
import json
import logging
import os
import time
import traceback
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db, SessionLocal
from app.models.talent import Talent, Tag, TalentTag, EntryLog, CardDimension
from app.middleware.auth_middleware import require_auth
from app.services.llm_service import update_talent_card, parse_pdf_content, parse_image_content, get_current_model_name, DEFAULT_PDF_PARSE_INSTRUCTIONS, DEFAULT_IMAGE_PARSE_INSTRUCTIONS
from app.services.pdf_service import extract_text_from_pdf, extract_markdown_from_pdf, pdf_to_images
from app.services.pinyin_service import get_pinyin_data

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/entry", tags=["entry"])

# Directory for saving uploaded PDFs before background processing
PDF_UPLOAD_DIR = os.path.join(os.environ.get("TEAMGR_DATA_DIR", "data"), "pdf-uploads")


def _ensure_pdf_upload_dir():
    os.makedirs(PDF_UPLOAD_DIR, exist_ok=True)


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

        # Apply new dimensions (validate each item is a dict, same as PDF/image paths)
        new_dims = result.get("new_dimensions", [])
        if isinstance(new_dims, list):
            new_dims = [d for d in new_dims if isinstance(d, dict)]
            _apply_new_dimensions(db, new_dims)

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


async def _process_pdf_from_file_bg(entry_log_id: int):
    """Background task: read saved PDF from disk, extract content, call LLM, update talent card.

    This is the complete PDF processing pipeline. It reads the PDF from
    data/pdf-uploads/{entry_log_id}.pdf, does ALL heavy work (image conversion,
    text extraction, LLM call), then updates the talent card.
    """
    t_start = time.monotonic()
    pdf_path = os.path.join(PDF_UPLOAD_DIR, f"{entry_log_id}.pdf")
    db = SessionLocal()
    try:
        # Load entry log and talent info
        entry_log = db.query(EntryLog).filter(EntryLog.id == entry_log_id).first()
        if not entry_log:
            logger.warning(f"Entry log {entry_log_id} not found, skipping")
            return
        talent = db.query(Talent).filter(Talent.id == entry_log.talent_id).first()
        if not talent:
            logger.warning(f"Talent {entry_log.talent_id} not found, skipping")
            return

        # Transition: uploaded → processing
        entry_log.status = "processing"
        db.commit()
        logger.info(f"[PDF] Starting processing for entry {entry_log_id} (talent: {talent.name})")

        # Read PDF from disk
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # --- Heavy processing (all moved from request handler) ---

        # 1. Convert PDF to images
        t0 = time.monotonic()
        pdf_images = pdf_to_images(pdf_bytes)
        logger.info(f"[TIMING] pdf_to_images ({len(pdf_images)} pages): {time.monotonic() - t0:.2f}s")
        if not pdf_images:
            raise ValueError("PDF中未识别到任何页面")

        # Update content with page count
        entry_log.content = f"{entry_log.content} ({len(pdf_images)}页)"
        db.commit()

        # 2. Extract structured markdown
        t1 = time.monotonic()
        pdf_markdown = ""
        try:
            pdf_markdown = extract_markdown_from_pdf(pdf_bytes)
        except Exception as e:
            logger.warning(f"Markdown extraction failed: {e}")
        logger.info(f"[TIMING] markdown extract: {time.monotonic() - t1:.2f}s ({len(pdf_markdown)} chars)")

        # 3. Extract pdfplumber text as fallback
        t2 = time.monotonic()
        pdf_text_fallback = ""
        try:
            pdf_text_fallback = extract_text_from_pdf(pdf_bytes)
        except Exception:
            pass
        logger.info(f"[TIMING] pdfplumber text extract: {time.monotonic() - t2:.2f}s")

        # 4. LLM parsing
        dimensions = _get_dimensions(db)
        t3 = time.monotonic()
        result = await parse_pdf_content(
            pdf_images=pdf_images,
            dimensions=dimensions,
            talent_name=talent.name,
            pdf_text_fallback=pdf_text_fallback,
            pdf_markdown=pdf_markdown,
        )
        logger.info(f"[TIMING] PDF LLM parse: {time.monotonic() - t3:.1f}s (entry {entry_log_id})")

        # Ensure result is a dict
        if not isinstance(result, dict):
            logger.warning(f"parse_pdf_content returned non-dict: {type(result)}")
            result = {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": []}

        # Re-fetch talent (may have been updated during long processing)
        talent = db.query(Talent).filter(Talent.id == entry_log.talent_id).first()
        if not talent:
            return

        # Apply new dimensions
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

        # Update entry log — include debug info
        best_text = pdf_markdown.strip() if pdf_markdown else pdf_text_fallback.strip()
        parse_mode = "text-first" if len(best_text) > 100 else "image-first"
        result["_debug"] = {
            "parse_mode": parse_mode,
            "extracted_text": best_text[:20000],
            "extracted_text_length": len(best_text),
        }
        entry_log.llm_response = json.dumps(result, ensure_ascii=False)
        entry_log.status = "done"
        entry_log.model_name = get_current_model_name()

        db.commit()
        logger.info(f"PDF processing done for entry {entry_log_id}, total: {time.monotonic() - t_start:.1f}s")

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
        # Clean up PDF file
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except OSError:
            pass
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
    """Upload a PDF resume. Phase 1: save to disk immediately. Phase 2: background processing.

    The upload completes in <1s (just file I/O + DB insert), so the user can
    safely close their laptop right after seeing the "已上传" confirmation.
    All heavy processing happens in the background task.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传PDF文件")

    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    # Phase 1: Read bytes and save to disk — fast, no heavy processing
    pdf_bytes = await file.read()

    # Create entry log with "uploaded" status (not "processing" yet)
    entry_log = EntryLog(
        talent_id=talent.id,
        content=f"[PDF上传] {file.filename}",
        source="pdf",
        status="uploaded",
    )
    db.add(entry_log)
    db.commit()
    db.refresh(entry_log)

    # Save PDF to disk
    _ensure_pdf_upload_dir()
    pdf_path = os.path.join(PDF_UPLOAD_DIR, f"{entry_log.id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    logger.info(f"[PDF] Saved {file.filename} ({len(pdf_bytes)} bytes) as entry {entry_log.id}")

    # Phase 2: Fire background processing (reads from disk, survives client disconnect)
    asyncio.create_task(_process_pdf_from_file_bg(entry_log.id))

    return {
        "message": "简历已上传，等待后台解析",
        "entry_id": entry_log.id,
        "talent_id": talent.id,
        "status": "uploaded",
    }


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB per image
MAX_IMAGE_COUNT = 10


async def _process_image_entry_bg(entry_log_id: int, talent_id: int,
                                   images: list[bytes],
                                   dimensions: list[dict], talent_name: str):
    """Background task: call VLM to parse uploaded images and update talent card."""
    t_start = time.monotonic()
    db = SessionLocal()
    try:
        t0 = time.monotonic()
        result = await parse_image_content(
            images=images,
            dimensions=dimensions,
            talent_name=talent_name,
        )
        logger.info(f"[TIMING] Image VLM parse: {time.monotonic() - t0:.1f}s (entry {entry_log_id})")

        if not isinstance(result, dict):
            logger.warning(f"parse_image_content returned non-dict: {type(result)}")
            result = {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": []}

        talent = db.query(Talent).filter(Talent.id == talent_id).first()
        if not talent:
            return

        # Apply new dimensions
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
            entry_log.model_name = get_current_model_name()

        db.commit()
        logger.info(f"Image LLM processing done for talent {talent_id}, entry {entry_log_id}, total: {time.monotonic() - t_start:.1f}s")

    except Exception as e:
        logger.error(f"Background image processing failed for entry {entry_log_id}: {e}\n{traceback.format_exc()}")
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


@router.post("/image")
async def upload_images(
    talent_id: int = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    _=Depends(require_auth),
):
    """Upload images (business card, screenshot, etc). Saves immediately, LLM processes in background."""
    if not files:
        raise HTTPException(status_code=400, detail="请上传至少一张图片")

    if len(files) > MAX_IMAGE_COUNT:
        raise HTTPException(status_code=400, detail=f"最多上传{MAX_IMAGE_COUNT}张图片")

    talent = db.query(Talent).filter(Talent.id == talent_id).first()
    if not talent:
        raise HTTPException(status_code=404, detail="人才不存在")

    # Validate and read images
    image_bytes_list = []
    filenames = []
    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"不支持的图片格式: {ext}")
        data = await f.read()
        if len(data) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail=f"图片 {f.filename} 太大（最大10MB）")
        image_bytes_list.append(data)
        filenames.append(f.filename or "unknown")

    dimensions = _get_dimensions(db)

    entry_log = EntryLog(
        talent_id=talent.id,
        content=f"[图片上传] {', '.join(filenames)} ({len(image_bytes_list)}张)",
        source="image",
        status="processing",
    )
    db.add(entry_log)
    db.commit()
    db.refresh(entry_log)

    asyncio.create_task(_process_image_entry_bg(
        entry_log_id=entry_log.id,
        talent_id=talent.id,
        images=image_bytes_list,
        dimensions=dimensions,
        talent_name=talent.name,
    ))

    return {
        "message": "图片已上传，后台解析中",
        "entry_id": entry_log.id,
        "talent_id": talent.id,
        "status": "processing",
    }


@router.get("/prompts/{prompt_type}")
async def get_entry_prompt(prompt_type: str, _=Depends(require_auth)):
    """Get editable prompt for pdf-parse or image-parse."""
    from app.config import get_instruction
    if prompt_type == "pdf-parse":
        return {
            "instructions": get_instruction("pdf_parse", DEFAULT_PDF_PARSE_INSTRUCTIONS),
            "default": DEFAULT_PDF_PARSE_INSTRUCTIONS,
        }
    elif prompt_type == "image-parse":
        return {
            "instructions": get_instruction("image_parse", DEFAULT_IMAGE_PARSE_INSTRUCTIONS),
            "default": DEFAULT_IMAGE_PARSE_INSTRUCTIONS,
        }
    else:
        raise HTTPException(status_code=400, detail=f"未知的 prompt 类型: {prompt_type}")


@router.put("/prompts/{prompt_type}")
async def save_entry_prompt(prompt_type: str, body: dict, _=Depends(require_auth)):
    """Save custom prompt for pdf-parse or image-parse."""
    from app.config import save_instruction
    instructions = body.get("instructions", "").strip()
    if prompt_type == "pdf-parse":
        save_instruction("pdf_parse", instructions)
    elif prompt_type == "image-parse":
        save_instruction("image_parse", instructions)
    else:
        raise HTTPException(status_code=400, detail=f"未知的 prompt 类型: {prompt_type}")
    return {"ok": True}


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
            "model_name": log.model_name or "",
            "llm_response": log.llm_response or "",
            "created_at": log.created_at.isoformat() if log.created_at else "",
        }
        for log in logs
    ]
