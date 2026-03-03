import json
import logging
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.talent import Talent, CardDimension, PresetQuestion, ScheduledQueryResult
from app.middleware.auth_middleware import require_auth
from app.services.llm_service import analyze_query_dimensions, answer_talent_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(require_auth)])


class ChatAnalyzeRequest(BaseModel):
    query: str


class ChatAnswerRequest(BaseModel):
    query: str
    dimension_keys: list[str]


class PresetQuestionCreate(BaseModel):
    question: str


class PresetQuestionUpdate(BaseModel):
    question: str | None = None
    is_scheduled: bool | None = None


def _get_dimensions(db: Session) -> list[dict]:
    dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
    return [{"key": d.key, "label": d.label, "schema": d.schema} for d in dims]


@router.post("/analyze")
async def chat_analyze(req: ChatAnalyzeRequest, db: Session = Depends(get_db)):
    """Step 1: Analyze which dimensions are relevant to the user's query."""
    dimensions = _get_dimensions(db)
    result = await analyze_query_dimensions(req.query, dimensions)
    return result


def _build_name_mapping(names: list[str]) -> tuple[dict, dict]:
    """Create bidirectional name-pseudonym mapping. Sorted by length desc to avoid substring conflicts."""
    charset = string.ascii_letters + string.digits
    name_to_pseudo, pseudo_to_name = {}, {}
    used = set()
    for name in sorted(names, key=len, reverse=True):
        if not name or name in name_to_pseudo:
            continue
        while True:
            pseudo = "T_" + "".join(secrets.choice(charset) for _ in range(5))
            if pseudo not in used:
                break
        used.add(pseudo)
        name_to_pseudo[name] = pseudo
        pseudo_to_name[pseudo] = name
    return name_to_pseudo, pseudo_to_name


def _replace_names_in_value(value, name_to_pseudo: dict, sorted_names: list[str]):
    """Recursively replace real names with pseudonyms in a value (str, list, or dict)."""
    if isinstance(value, str):
        for name in sorted_names:
            value = value.replace(name, name_to_pseudo[name])
        return value
    if isinstance(value, list):
        return [_replace_names_in_value(item, name_to_pseudo, sorted_names) for item in value]
    if isinstance(value, dict):
        return {k: _replace_names_in_value(v, name_to_pseudo, sorted_names) for k, v in value.items()}
    return value


def _restore_names(text: str, pseudo_to_name: dict) -> str:
    """Replace pseudonyms back to real names. Sorted by length desc to avoid partial matches."""
    for pseudo in sorted(pseudo_to_name, key=len, reverse=True):
        text = text.replace(pseudo, pseudo_to_name[pseudo])
    return text


@router.post("/answer")
async def chat_answer(req: ChatAnswerRequest, db: Session = Depends(get_db)):
    """Step 2: Extract relevant dimension data, pseudonymize names, answer query, restore names."""
    all_talents = db.query(Talent).all()

    # Build name privacy mapping
    real_names = [t.name for t in all_talents if t.name]
    name_to_pseudo, pseudo_to_name = _build_name_mapping(real_names)
    sorted_names = sorted(name_to_pseudo.keys(), key=len, reverse=True)

    # Build context JSON with pseudonymized names
    talents_context = []
    for t in all_talents:
        card = t.card_data or {}
        entry = {
            "name": name_to_pseudo.get(t.name, t.name),
            "current_role": t.current_role or "",
            "department": t.department or "",
            "summary": t.summary or "",
        }
        for key in req.dimension_keys:
            if key in card:
                entry[key] = card[key]

        # Replace real names in all values (handles nested structures too)
        for field_key in list(entry.keys()):
            if field_key == "name":
                continue  # already pseudonymized
            entry[field_key] = _replace_names_in_value(entry[field_key], name_to_pseudo, sorted_names)

        talents_context.append(entry)

    context_json = json.dumps(talents_context, ensure_ascii=False, indent=1)
    if len(context_json) > 30000:
        logger.warning(f"Talent context truncated from {len(context_json)} to 30000 chars")
        context_json = context_json[:30000]

    result = await answer_talent_query(req.query, context_json, req.dimension_keys)
    raw_answer = result.get("answer", "")
    final_answer = _restore_names(raw_answer, pseudo_to_name)

    return {
        "raw_answer": raw_answer,
        "final_answer": final_answer,
        "name_mapping": name_to_pseudo,
        "talent_count": len(all_talents),
        "dimensions_used": req.dimension_keys,
    }


# --- Preset Questions CRUD ---

def _preset_to_dict(p: PresetQuestion) -> dict:
    return {
        "id": p.id,
        "question": p.question,
        "is_scheduled": p.is_scheduled,
        "sort_order": p.sort_order,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


@router.get("/presets")
async def list_presets(db: Session = Depends(get_db)):
    presets = db.query(PresetQuestion).order_by(PresetQuestion.sort_order).all()
    return [_preset_to_dict(p) for p in presets]


@router.post("/presets")
async def create_preset(body: PresetQuestionCreate, db: Session = Depends(get_db)):
    max_order = db.query(PresetQuestion).count()
    preset = PresetQuestion(question=body.question, sort_order=max_order)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _preset_to_dict(preset)


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: int, body: PresetQuestionUpdate, db: Session = Depends(get_db)):
    preset = db.query(PresetQuestion).filter(PresetQuestion.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="预设问题不存在")
    if body.question is not None:
        preset.question = body.question
    if body.is_scheduled is not None:
        preset.is_scheduled = body.is_scheduled
    db.commit()
    db.refresh(preset)
    return _preset_to_dict(preset)


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = db.query(PresetQuestion).filter(PresetQuestion.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="预设问题不存在")
    db.delete(preset)
    db.commit()
    return {"message": "已删除"}


# --- Scheduled Query Results ---

@router.get("/scheduled-results")
async def list_scheduled_results(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    results = (
        db.query(ScheduledQueryResult)
        .order_by(ScheduledQueryResult.generated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "preset_question_id": r.preset_question_id,
            "question_snapshot": r.question_snapshot,
            "answer": r.answer,
            "model_name": r.model_name,
            "generated_at": r.generated_at.isoformat() if r.generated_at else "",
        }
        for r in results
    ]
