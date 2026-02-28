import json
import logging
import secrets
import string
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.talent import Talent, CardDimension
from app.middleware.auth_middleware import require_auth
from app.services.llm_service import analyze_query_dimensions, answer_talent_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(require_auth)])


class ChatAnalyzeRequest(BaseModel):
    query: str


class ChatAnswerRequest(BaseModel):
    query: str
    dimension_keys: list[str]


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
