import asyncio
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.talent import IdeaFragment, IdeaInputLog, IdeaInsight

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ideas", tags=["ideas"])


class IdeaInput(BaseModel):
    content: str


# ---- Fragments ----

@router.get("/fragments")
def list_fragments(db: Session = Depends(get_db)):
    fragments = db.query(IdeaFragment).order_by(IdeaFragment.updated_at.desc()).all()
    return [
        {
            "id": f.id,
            "title": f.title,
            "content": f.content,
            "category": f.category,
            "tags": f.tags or [],
            "source_input_ids": f.source_input_ids or [],
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }
        for f in fragments
    ]


@router.delete("/fragments/{fragment_id}")
def delete_fragment(fragment_id: int, db: Session = Depends(get_db)):
    frag = db.query(IdeaFragment).filter(IdeaFragment.id == fragment_id).first()
    if not frag:
        raise HTTPException(status_code=404, detail="Fragment not found")
    db.delete(frag)
    db.commit()
    return {"ok": True}


# ---- Input & Classification ----

@router.post("/input")
async def submit_idea(body: IdeaInput, db: Session = Depends(get_db)):
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    log = IdeaInputLog(raw_text=body.content.strip(), status="processing")
    db.add(log)
    db.commit()
    db.refresh(log)

    # Run LLM classification in background
    asyncio.create_task(_process_idea(log.id, body.content.strip()))

    return {
        "input_id": log.id,
        "status": "processing",
    }


@router.post("/input/stream")
async def submit_idea_stream(body: IdeaInput, db: Session = Depends(get_db)):
    """Submit idea with SSE streaming of LLM classification process."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    raw_text = body.content.strip()

    log = IdeaInputLog(raw_text=raw_text, status="processing")
    db.add(log)
    db.commit()
    db.refresh(log)
    input_log_id = log.id

    # Get existing fragments for context
    existing = db.query(IdeaFragment).all()
    existing_dicts = [
        {
            "id": f.id,
            "title": f.title,
            "content": f.content,
            "category": f.category,
            "tags": f.tags or [],
        }
        for f in existing
    ]

    from app.services.llm_service import (
        _get_local_model_config, _extract_json, _record_llm_usage,
        _strip_think_tags, _LOCAL_CALL_TIMEOUT, get_current_model_name,
    )

    # Build prompt (same as classify_idea)
    existing_desc = ""
    if existing_dicts:
        items = []
        for f in existing_dicts[:50]:
            items.append(
                f"ID={f['id']}, 标题={f['title']}, 分类={f['category']}, "
                f"标签={','.join(f.get('tags', []))}, 内容={f['content'][:100]}"
            )
        existing_desc = "\n".join(items)

    prompt = f"""你是一个灵感整理助手。用户输入了一段灵感/想法，请你：
1. 将其分类、打标签、整理为一个或多个"灵感碎片"
2. 如果新输入与已有碎片高度相关，应合并到已有碎片（action="merge"，并提供merge_target_id）
3. 如果是全新的主题，则创建新条目（action="new"）
4. 一次输入可能包含多个不同的灵感，请拆分为多个碎片

## 用户输入:
{raw_text}

## 已有灵感碎片:
{existing_desc if existing_desc else "（暂无）"}

请严格返回以下JSON格式（不要代码块）:
{{
  "fragments": [
    {{
      "action": "new 或 merge",
      "merge_target_id": null,
      "title": "简短标题",
      "content": "整理后的内容（合并时应包含新旧内容的融合）",
      "category": "分类名",
      "tags": ["标签1", "标签2"]
    }}
  ]
}}"""

    async def event_stream():
        import threading
        from app.database import SessionLocal

        full_text = ""
        usage = None
        t0 = time.monotonic()

        try:
            from app.config import get_gemini_config, get_model_defaults

            classify_model = get_model_defaults().get("idea-classify") or get_current_model_name()
            local_cfg = _get_local_model_config(classify_model)

            if local_cfg:
                # Local model: use streaming via OpenAI-compatible SSE
                import httpx
                api_base = local_cfg["api_base"].rstrip("/")
                api_key = local_cfg.get("api_key", "")
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                payload = {
                    "messages": [
                        {"role": "system", "content": "请直接回答，不要输出思考过程。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream": True,
                }
                if local_cfg.get("model_id"):
                    payload["model"] = local_cfg["model_id"]

                async with httpx.AsyncClient(timeout=_LOCAL_CALL_TIMEOUT) as client:
                    async with client.stream(
                        "POST", f"{api_base}/chat/completions",
                        json=payload, headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data["choices"][0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    full_text += text
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass

                full_text = _strip_think_tags(full_text)
                duration_ms = int((time.monotonic() - t0) * 1000)
                _record_llm_usage(classify_model, "idea-classify", duration_ms, 0, 0)

            else:
                # Gemini model: stream with thinking support
                from google import genai
                from google.genai import types as genai_types

                cfg = get_gemini_config()
                api_key = cfg.get("api_key", "")
                if not api_key or api_key == "your-gemini-api-key-here":
                    yield f"data: {json.dumps({'type': 'error', 'content': 'LLM模型不可用'}, ensure_ascii=False)}\n\n"
                    return

                gclient = genai.Client(api_key=api_key)
                queue = asyncio.Queue()
                loop = asyncio.get_event_loop()
                stream_error = [None]

                def produce():
                    try:
                        response = gclient.models.generate_content_stream(
                            model=classify_model,
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
                _record_llm_usage(classify_model, "idea-classify", duration_ms, isl, osl)

            # Parse result and save fragments
            result = _extract_json(full_text)

            sdb = SessionLocal()
            try:
                input_log = sdb.query(IdeaInputLog).filter(IdeaInputLog.id == input_log_id).first()
                if input_log:
                    input_log.llm_response = json.dumps(result, ensure_ascii=False)

                fragments_data = result.get("fragments", [])
                for frag_data in fragments_data:
                    action = frag_data.get("action", "new")
                    merge_id = frag_data.get("merge_target_id")

                    if action == "merge" and merge_id:
                        target = sdb.query(IdeaFragment).filter(IdeaFragment.id == merge_id).first()
                        if target:
                            target.content = frag_data.get("content", target.content)
                            target.title = frag_data.get("title", target.title)
                            target.category = frag_data.get("category", target.category)
                            old_tags = set(target.tags or [])
                            new_tags = set(frag_data.get("tags", []))
                            target.tags = list(old_tags | new_tags)
                            sources = list(target.source_input_ids or [])
                            sources.append(input_log_id)
                            target.source_input_ids = sources
                            target.updated_at = datetime.utcnow()
                            continue

                    new_frag = IdeaFragment(
                        title=frag_data.get("title", "未命名灵感"),
                        content=frag_data.get("content", raw_text),
                        category=frag_data.get("category", "未分类"),
                        tags=frag_data.get("tags", []),
                        source_input_ids=[input_log_id],
                    )
                    sdb.add(new_frag)

                if input_log:
                    input_log.status = "done"
                sdb.commit()

                yield f"data: {json.dumps({'type': 'done', 'fragments': fragments_data}, ensure_ascii=False)}\n\n"
            finally:
                sdb.close()

        except json.JSONDecodeError:
            _mark_input_failed(input_log_id, "LLM返回格式错误")
            yield f"data: {json.dumps({'type': 'error', 'content': 'LLM返回格式错误'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Idea stream error: {e}")
            _mark_input_failed(input_log_id, str(e))
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _mark_input_failed(input_log_id: int, error: str):
    from app.database import SessionLocal
    sdb = SessionLocal()
    try:
        log = sdb.query(IdeaInputLog).filter(IdeaInputLog.id == input_log_id).first()
        if log:
            log.status = "failed"
            log.llm_response = error
            sdb.commit()
    except Exception:
        pass
    finally:
        sdb.close()


async def _process_idea(input_log_id: int, raw_text: str):
    from app.database import SessionLocal
    from app.services.llm_service import classify_idea

    db = SessionLocal()
    try:
        # Get existing fragments for context
        existing = db.query(IdeaFragment).all()
        existing_dicts = [
            {
                "id": f.id,
                "title": f.title,
                "content": f.content,
                "category": f.category,
                "tags": f.tags or [],
            }
            for f in existing
        ]

        result = await classify_idea(raw_text, existing_dicts)

        input_log = db.query(IdeaInputLog).filter(IdeaInputLog.id == input_log_id).first()
        if not input_log:
            return

        import json
        input_log.llm_response = json.dumps(result, ensure_ascii=False)

        fragments_data = result.get("fragments", [])
        for frag_data in fragments_data:
            action = frag_data.get("action", "new")
            merge_id = frag_data.get("merge_target_id")

            if action == "merge" and merge_id:
                target = db.query(IdeaFragment).filter(IdeaFragment.id == merge_id).first()
                if target:
                    target.content = frag_data.get("content", target.content)
                    target.title = frag_data.get("title", target.title)
                    target.category = frag_data.get("category", target.category)
                    # Merge tags
                    old_tags = set(target.tags or [])
                    new_tags = set(frag_data.get("tags", []))
                    target.tags = list(old_tags | new_tags)
                    # Track source
                    sources = list(target.source_input_ids or [])
                    sources.append(input_log_id)
                    target.source_input_ids = sources
                    target.updated_at = datetime.utcnow()
                    continue

            # New fragment
            new_frag = IdeaFragment(
                title=frag_data.get("title", "未命名灵感"),
                content=frag_data.get("content", raw_text),
                category=frag_data.get("category", "未分类"),
                tags=frag_data.get("tags", []),
                source_input_ids=[input_log_id],
            )
            db.add(new_frag)

        input_log.status = "done"
        db.commit()
        logger.info(f"Idea input {input_log_id} processed: {len(fragments_data)} fragment(s)")

    except Exception as e:
        logger.error(f"Failed to process idea input {input_log_id}: {e}")
        try:
            input_log = db.query(IdeaInputLog).filter(IdeaInputLog.id == input_log_id).first()
            if input_log:
                input_log.status = "failed"
                input_log.llm_response = str(e)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.get("/input/status/{input_id}")
def get_input_status(input_id: int, db: Session = Depends(get_db)):
    log = db.query(IdeaInputLog).filter(IdeaInputLog.id == input_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Input log not found")
    return {"id": log.id, "status": log.status}


# ---- Input History ----

@router.get("/history")
def list_input_history(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    total = db.query(IdeaInputLog).count()
    logs = (
        db.query(IdeaInputLog)
        .order_by(IdeaInputLog.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [
            {
                "id": l.id,
                "raw_text": l.raw_text,
                "status": l.status,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


# ---- Insights ----

@router.get("/insights")
def list_insights(db: Session = Depends(get_db)):
    insights = (
        db.query(IdeaInsight)
        .order_by(IdeaInsight.created_at.desc())
        .all()
    )
    return [
        {
            "id": i.id,
            "content": i.content,
            "reasoning": i.reasoning,
            "liked": i.liked,
            "generated_date": i.generated_date,
            "model_name": i.model_name or "",
            "created_at": i.created_at.isoformat() if i.created_at else None,
        }
        for i in insights
    ]


@router.post("/insights/{insight_id}/like")
def like_insight(insight_id: int, db: Session = Depends(get_db)):
    insight = db.query(IdeaInsight).filter(IdeaInsight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.liked = True
    db.commit()
    return {"ok": True, "liked": True}


@router.delete("/insights/{insight_id}/like")
def unlike_insight(insight_id: int, db: Session = Depends(get_db)):
    insight = db.query(IdeaInsight).filter(IdeaInsight.id == insight_id).first()
    if not insight:
        raise HTTPException(status_code=404, detail="Insight not found")
    insight.liked = False
    db.commit()
    return {"ok": True, "liked": False}


@router.post("/insights/generate")
async def trigger_insight_generation(db: Session = Depends(get_db)):
    """Manually trigger insight generation (same logic as daily cron)."""
    await run_daily_idea_aggregation()
    return {"ok": True}


# ---- Daily Aggregation Job ----

async def run_daily_idea_aggregation():
    """Run by scheduler at 3 AM daily. Aggregates all fragments into insights."""
    from app.database import SessionLocal
    from app.config import get_model_defaults
    from app.services.llm_service import aggregate_idea_insights, get_current_model_name

    db = SessionLocal()
    try:
        # Get all fragments
        fragments = db.query(IdeaFragment).all()
        if not fragments:
            logger.info("No idea fragments to aggregate")
            return

        frag_dicts = [
            {
                "id": f.id,
                "title": f.title,
                "content": f.content,
                "category": f.category,
                "tags": f.tags or [],
            }
            for f in fragments
        ]

        # Get previously liked insights (to avoid repeating)
        liked = db.query(IdeaInsight).filter(IdeaInsight.liked == True).all()
        liked_contents = [i.content for i in liked]

        # Remove un-liked insights from previous days (keep today's and liked ones)
        _CN_TZ = timezone(timedelta(hours=8))
        today = datetime.now(_CN_TZ).strftime("%Y-%m-%d")
        stale = (
            db.query(IdeaInsight)
            .filter(IdeaInsight.liked == False, IdeaInsight.generated_date != today)
            .all()
        )
        for s in stale:
            db.delete(s)
        if stale:
            db.commit()
            logger.info(f"Removed {len(stale)} un-liked stale insights")

        # Generate new insights
        insight_model = get_model_defaults().get("idea-insight") or get_current_model_name()
        insights = await aggregate_idea_insights(frag_dicts, liked_contents)

        for ins in insights:
            new_insight = IdeaInsight(
                content=ins.get("content", ""),
                reasoning=ins.get("reasoning", ""),
                liked=False,
                generated_date=today,
                model_name=insight_model,
            )
            db.add(new_insight)

        db.commit()
        logger.info(f"Generated {len(insights)} new idea insights for {today}")

    except Exception as e:
        logger.error(f"Daily idea aggregation failed: {e}")
    finally:
        db.close()


def _build_idea_tag_organize_prompt(tag_names: list[str]) -> str:
    return f"""你是一个标签分类专家。请完成以下两个任务：

## 任务1：合并同义标签
找出语义相同或高度相似的标签组，选择最简洁准确的一个作为保留名，其余作为待合并项。
判断标准：含义本质相同只是措辞不同。
注意：含义不同的标签不要合并。

## 任务2：分层归类
将合并后的标签归类为一级标签（大分类）和二级标签（具体标签）的层级结构。
要求：
1. 一级标签是新创建的大分类名称，数量控制在3-8个
2. 每个保留的标签都必须归入某个一级标签下作为二级标签
3. 一级标签名称要简洁、有概括性
4. 所有保留的标签都必须被分配，不能遗漏

现有标签列表：
{json.dumps(tag_names, ensure_ascii=False)}

请严格按以下JSON格式返回，不要包含其他内容：
{{
  "merges": [
    {{"keep": "保留的标签名", "remove": ["待合并标签1", "待合并标签2"]}}
  ],
  "categories": [
    {{
      "name": "一级标签名称",
      "children": ["二级标签1", "二级标签2"]
    }}
  ]
}}

如果没有需要合并的标签，merges 返回空数组 []。"""


@router.post("/tags/organize")
async def organize_idea_tags(db: Session = Depends(get_db)):
    """Use LLM to organize idea fragment tags with SSE streaming."""

    # Collect all unique tags from fragments
    fragments = db.query(IdeaFragment).all()
    all_tags = set()
    for f in fragments:
        for tag in (f.tags or []):
            all_tags.add(tag)

    if not all_tags:
        raise HTTPException(status_code=400, detail="没有标签需要整理")

    tag_names = sorted(all_tags)
    prompt = _build_idea_tag_organize_prompt(tag_names)

    async def event_stream():
        import threading

        full_text = ""
        usage = None
        t0 = time.monotonic()

        try:
            from app.config import get_gemini_config, get_model_defaults
            from app.services.llm_service import (
                _get_local_model_config, _extract_json, _record_llm_usage,
                _strip_think_tags, _LOCAL_CALL_TIMEOUT, get_current_model_name,
            )

            organize_model = get_model_defaults().get("organize-tags") or get_current_model_name()
            local_cfg = _get_local_model_config(organize_model)

            if local_cfg:
                import httpx
                api_base = local_cfg["api_base"].rstrip("/")
                api_key = local_cfg.get("api_key", "")
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                payload = {
                    "messages": [
                        {"role": "system", "content": "请直接回答，不要输出思考过程。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "stream": True,
                }
                if local_cfg.get("model_id"):
                    payload["model"] = local_cfg["model_id"]

                async with httpx.AsyncClient(timeout=_LOCAL_CALL_TIMEOUT) as client:
                    async with client.stream(
                        "POST", f"{api_base}/chat/completions",
                        json=payload, headers=headers,
                    ) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk_data = json.loads(data_str)
                                delta = chunk_data["choices"][0].get("delta", {})
                                text = delta.get("content", "")
                                if text:
                                    full_text += text
                                    yield f"data: {json.dumps({'type': 'chunk', 'content': text}, ensure_ascii=False)}\n\n"
                            except (json.JSONDecodeError, KeyError, IndexError):
                                pass

                full_text = _strip_think_tags(full_text)
                duration_ms = int((time.monotonic() - t0) * 1000)
                _record_llm_usage(organize_model, "organize-tags", duration_ms, 0, 0)

            else:
                from google import genai
                from google.genai import types as genai_types

                cfg = get_gemini_config()
                api_key = cfg.get("api_key", "")
                if not api_key or api_key == "your-gemini-api-key-here":
                    yield f"data: {json.dumps({'type': 'error', 'content': 'LLM模型不可用'}, ensure_ascii=False)}\n\n"
                    return

                gclient = genai.Client(api_key=api_key)
                queue = asyncio.Queue()
                loop = asyncio.get_event_loop()
                stream_error = [None]

                def produce():
                    try:
                        response = gclient.models.generate_content_stream(
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
            result = _extract_json(full_text)

            # Apply merges: rename tags in all fragments
            from app.database import SessionLocal
            sdb = SessionLocal()
            try:
                merges = result.get("merges", [])
                merge_descs = []
                rename_map = {}  # old_name -> new_name
                for merge in merges:
                    keep = merge.get("keep", "")
                    removes = merge.get("remove", [])
                    if keep and removes:
                        for rm in removes:
                            rename_map[rm] = keep
                        merge_descs.append(f"{', '.join(removes)} → {keep}")

                if merge_descs:
                    # Apply renames to all fragments
                    all_frags = sdb.query(IdeaFragment).all()
                    for frag in all_frags:
                        tags = frag.tags or []
                        new_tags = []
                        seen = set()
                        for t in tags:
                            mapped = rename_map.get(t, t)
                            if mapped not in seen:
                                new_tags.append(mapped)
                                seen.add(mapped)
                        if new_tags != tags:
                            frag.tags = new_tags
                    sdb.commit()
                    yield f"data: {json.dumps({'type': 'merge', 'merges': merge_descs}, ensure_ascii=False)}\n\n"

                # Build categories response
                categories = result.get("categories", [])

                # Collect final unique tags
                all_frags = sdb.query(IdeaFragment).all()
                final_tags = set()
                for frag in all_frags:
                    for t in (frag.tags or []):
                        final_tags.add(t)

                yield f"data: {json.dumps({'type': 'done', 'categories': categories, 'all_tags': sorted(final_tags)}, ensure_ascii=False)}\n\n"
            finally:
                sdb.close()

        except json.JSONDecodeError:
            yield f"data: {json.dumps({'type': 'error', 'content': 'LLM返回格式错误'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Idea tag organize error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def run_daily_idea_aggregation_sync():
    """Synchronous wrapper for APScheduler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_daily_idea_aggregation())
        else:
            loop.run_until_complete(run_daily_idea_aggregation())
    except RuntimeError:
        asyncio.run(run_daily_idea_aggregation())
