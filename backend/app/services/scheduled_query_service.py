import asyncio
import json
import logging
import secrets
import string
from datetime import datetime

logger = logging.getLogger(__name__)


def _build_name_mapping(names: list[str]) -> tuple[dict, dict]:
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
    for pseudo in sorted(pseudo_to_name, key=len, reverse=True):
        text = text.replace(pseudo, pseudo_to_name[pseudo])
    return text


async def _run_single_query(question: str) -> str:
    """Run the full 2-step LLM flow for a single question. Returns the final answer."""
    from app.database import SessionLocal
    from app.models.talent import Talent, CardDimension
    from app.models.team import TeamMember
    from app.services.llm_service import analyze_query_dimensions, answer_talent_query

    db = SessionLocal()
    try:
        # Step 1: Analyze dimensions
        dims = db.query(CardDimension).order_by(CardDimension.sort_order).all()
        dimensions = [{"key": d.key, "label": d.label, "schema": d.schema} for d in dims]
        analysis = await analyze_query_dimensions(question, dimensions)
        relevant_dims = analysis.get("relevant_dimensions", [])

        if not relevant_dims:
            return "未找到相关维度，无法回答该问题。"

        # Step 2: Build context with name privacy (only talents with team affiliation)
        team_talent_ids = db.query(TeamMember.talent_id).distinct().subquery()
        all_talents = db.query(Talent).filter(Talent.id.in_(team_talent_ids)).all()
        real_names = [t.name for t in all_talents if t.name]
        name_to_pseudo, pseudo_to_name = _build_name_mapping(real_names)
        sorted_names = sorted(name_to_pseudo.keys(), key=len, reverse=True)

        dimension_keys = [d["key"] for d in relevant_dims]
        talents_context = []
        for t in all_talents:
            card = t.card_data or {}
            entry = {
                "name": name_to_pseudo.get(t.name, t.name),
                "current_role": t.current_role or "",
                "department": t.department or "",
                "summary": t.summary or "",
            }
            for key in dimension_keys:
                if key in card:
                    entry[key] = card[key]
            for field_key in list(entry.keys()):
                if field_key == "name":
                    continue
                entry[field_key] = _replace_names_in_value(
                    entry[field_key], name_to_pseudo, sorted_names
                )
            talents_context.append(entry)

        context_json = json.dumps(talents_context, ensure_ascii=False, indent=1)
        if len(context_json) > 30000:
            context_json = context_json[:30000]

        result = await answer_talent_query(
            question, context_json, dimension_keys
        )
        raw_answer = result.get("answer", "")
        return _restore_names(raw_answer, pseudo_to_name)
    finally:
        db.close()


def run_scheduled_queries():
    """Entry point called by APScheduler. Runs in a thread, uses asyncio.run()."""
    logger.info("Starting scheduled query job...")

    from app.database import SessionLocal
    from app.models.talent import PresetQuestion, ScheduledQueryResult

    db = SessionLocal()
    try:
        scheduled = db.query(PresetQuestion).filter(PresetQuestion.is_scheduled == True).all()
        if not scheduled:
            logger.info("No scheduled preset questions found. Skipping.")
            return

        logger.info(f"Found {len(scheduled)} scheduled question(s) to process.")

        for preset in scheduled:
            try:
                answer = asyncio.run(_run_single_query(preset.question))
                # Delete old results for this preset, only keep the latest
                db.query(ScheduledQueryResult).filter(
                    ScheduledQueryResult.preset_question_id == preset.id
                ).delete()
                from app.config import get_model_defaults
                from app.services.llm_service import get_current_model_name
                effective_model = get_model_defaults().get("chat-answer") or get_current_model_name()
                result = ScheduledQueryResult(
                    preset_question_id=preset.id,
                    question_snapshot=preset.question,
                    answer=answer,
                    model_name=effective_model,
                    generated_at=datetime.utcnow(),
                )
                db.add(result)
                db.commit()
                logger.info(f"Scheduled query completed: '{preset.question[:30]}...'")
            except Exception as e:
                logger.error(f"Scheduled query failed for '{preset.question[:30]}...': {e}")
                db.rollback()
    finally:
        db.close()

    logger.info("Scheduled query job finished.")
