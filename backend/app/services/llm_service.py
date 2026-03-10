import asyncio
import json
import logging
import re
import time
from typing import Optional

import google.generativeai as genai
import httpx
from app.config import get_gemini_config, get_local_models_config

logger = logging.getLogger(__name__)


def _record_llm_usage(model_name: str, call_type: str, duration_ms: int, input_tokens: int, output_tokens: int):
    """Record LLM usage to database. Wrapped in try/except to never break main flow."""
    try:
        from app.database import SessionLocal
        from app.models.talent import LLMUsageLog
        db = SessionLocal()
        try:
            log = LLMUsageLog(
                model_name=model_name,
                call_type=call_type,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            db.add(log)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to record LLM usage: {e}")

_model_instance = None
_current_model_name = None


def _get_local_model_config(model_name: str) -> dict | None:
    """Return config dict for a local model, or None if not found."""
    for m in get_local_models_config():
        if m.get("name") == model_name:
            return m
    return None


def _get_model():
    """Get a Gemini model instance. Falls back to first Gemini model if current is local."""
    global _model_instance, _current_model_name
    cfg = get_gemini_config()
    api_key = cfg.get("api_key", "")
    model_name = cfg.get("current_model", "gemini-3-flash-preview")

    # If current model is local, fall back to first Gemini model (for multimodal)
    if _get_local_model_config(model_name):
        available = cfg.get("available_models", ["gemini-2.5-flash"])
        model_name = available[0] if available else "gemini-2.5-flash"

    if not api_key or api_key == "your-gemini-api-key-here":
        logger.warning("Gemini API key not configured. LLM features will not work.")
        return None

    if _model_instance is None or _current_model_name != model_name:
        genai.configure(api_key=api_key)
        _model_instance = genai.GenerativeModel(model_name)
        _current_model_name = model_name
        logger.info(f"Gemini model initialized: {model_name}")

    return _model_instance


def _get_model_for_override(model_name: str):
    """Create a one-off GenerativeModel instance for a specific model name.
    Does NOT affect the global _model_instance cache."""
    cfg = get_gemini_config()
    api_key = cfg.get("api_key", "")
    if not api_key or api_key == "your-gemini-api-key-here":
        return None
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


_LOCAL_CALL_TIMEOUT = 300.0

# Regex to strip <think>...</think> blocks from model output
_THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>\s*", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks (Qwen3 thinking mode output).
    Also handles unclosed <think> tags (truncated responses).
    """
    text = _THINK_TAG_RE.sub("", text)
    # Handle unclosed <think> at the start (truncated by max_tokens)
    text = re.sub(r"<think>[\s\S]*$", "", text)
    return text.strip()


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response text.
    Handles: raw JSON, ```json code blocks, mixed text with JSON.
    Raises json.JSONDecodeError if no valid JSON found.
    """
    text = text.strip()
    # 1. Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2. Try extracting from markdown code blocks
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # 3. Try finding first { ... } block
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise json.JSONDecodeError("No valid JSON found in response", text, 0)


async def _call_local_model(prompt: str, local_cfg: dict) -> tuple[str, int, int]:
    """Call a local model via OpenAI-compatible chat completions API.
    Returns (text, prompt_tokens, completion_tokens).
    """
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
    }
    # Include model field only if explicitly configured (some engines like TACO-X
    # expect exact model_dir path, so we skip it when not specified)
    if local_cfg.get("model_id"):
        payload["model"] = local_cfg["model_id"]

    async with httpx.AsyncClient(timeout=_LOCAL_CALL_TIMEOUT) as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        isl = usage.get("prompt_tokens", 0)
        osl = usage.get("completion_tokens", 0)
        return _strip_think_tags(content), isl, osl


async def _call_model_text(
    prompt: str,
    call_type: str = "",
    model_override: str | None = None,
) -> str | None:
    """Unified text generation that routes between Gemini and local models.
    Returns response text, or None if no model is configured.
    """
    # Priority: explicit override > per-call-type default > global default
    if not model_override and call_type:
        from app.config import get_model_defaults
        per_type = get_model_defaults().get(call_type)
        if per_type:
            model_override = per_type
    effective_model = model_override or get_current_model_name()
    local_cfg = _get_local_model_config(effective_model)

    t0 = time.monotonic()

    if local_cfg:
        text, isl, osl = await _call_local_model(prompt, local_cfg)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Local {effective_model} {call_type}: {duration_ms}ms (ISL={isl}, OSL={osl})")
        _record_llm_usage(effective_model, call_type, duration_ms, isl, osl)
        return text

    # Gemini path
    if model_override:
        model = _get_model_for_override(model_override)
        eff_name = model_override
    else:
        model = _get_model()
        eff_name = _current_model_name or "unknown"

    if not model:
        return None

    response = await asyncio.to_thread(model.generate_content, prompt)
    duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(f"[TIMING] Gemini {call_type}: {duration_ms}ms")

    usage = getattr(response, 'usage_metadata', None)
    isl = getattr(usage, 'prompt_token_count', 0) or 0
    osl = getattr(usage, 'candidates_token_count', 0) or 0
    _record_llm_usage(eff_name, call_type, duration_ms, isl, osl)

    return response.text.strip()


def get_current_model_name() -> str:
    cfg = get_gemini_config()
    explicit = cfg.get("current_model")
    if explicit:
        return explicit
    # Default to first local model if available, otherwise Gemini
    local_models = get_local_models_config()
    if local_models:
        return local_models[0]["name"]
    return "gemini-2.5-flash"


def get_available_models() -> list:
    """Return list of available models with location metadata.
    Each item: {"name": str, "location": "network" | "local"}
    """
    cfg = get_gemini_config()
    gemini_models = cfg.get(
        "available_models",
        [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-3.1-pro-preview",
        ],
    )
    result = [{"name": m, "location": "network"} for m in gemini_models]
    for m in get_local_models_config():
        result.append({"name": m["name"], "location": "local"})
    return result


async def update_talent_card(
    user_input: str,
    existing_card_data: dict,
    dimensions: list[dict],
    talent_name: str = "",
) -> dict:
    """Use LLM to process user input and update talent card data.

    Returns: {
        "card_data": updated card data dict,
        "summary": one-line summary,
        "suggested_tags": list of tag strings,
        "new_dimensions": list of {key, label, schema} if LLM suggests new dimensions
    }
    """
    dimensions_desc = ", ".join(f"{d['key']}({d['label']})" for d in dimensions)

    # Only include non-empty dimensions in card_data to reduce prompt size
    compact_card = {k: v for k, v in existing_card_data.items()
                    if v and v != {} and v != [] and v != ""}

    prompt = f"""将用户输入的信息提取到人才卡片维度中。

人才: {talent_name or '未命名'}
可用维度: {dimensions_desc}
已有数据: {json.dumps(compact_card, ensure_ascii=False)}
新输入: {user_input}

只返回JSON（不要代码块），只包含需要新增或修改的维度，不要重复已有不变的数据:
{{"card_updates": {{"维度key": {{变更字段}}}}, "summary": "一句话总结此人", "suggested_tags": ["原子化标签"], "new_dimensions": []}}"""

    try:
        text = await _call_model_text(prompt, call_type="text-entry")
        if text is None:
            return {
                "card_data": existing_card_data,
                "summary": "",
                "suggested_tags": [],
                "new_dimensions": [],
            }
        result = _extract_json(text)

        # Merge card_updates into existing data (incremental update)
        updates = result.get("card_updates") or result.get("card_data") or {}
        merged = dict(existing_card_data)
        for dim_key, dim_val in updates.items():
            if isinstance(dim_val, dict) and isinstance(merged.get(dim_key), dict):
                merged[dim_key] = {**merged[dim_key], **dim_val}
            else:
                merged[dim_key] = dim_val

        return {
            "card_data": merged,
            "summary": result.get("summary", ""),
            "suggested_tags": result.get("suggested_tags", []),
            "new_dimensions": result.get("new_dimensions", []),
        }
    except Exception as e:
        logger.error(f"LLM card update failed: {e}")
        return {
            "card_data": existing_card_data,
            "summary": "",
            "suggested_tags": [],
            "new_dimensions": [],
        }


async def parse_pdf_content(
    pdf_images: list[bytes],
    dimensions: list[dict],
    talent_name: str = "",
    pdf_text_fallback: str = "",
) -> dict:
    """Use VLM (multimodal) to extract structured info from PDF resume images.

    Args:
        pdf_images: List of PNG image bytes (one per page)
        dimensions: Card dimension definitions
        talent_name: Known talent name (optional)
        pdf_text_fallback: Text extracted by pdfplumber as supplementary context

    Returns: dict with extracted_info, card_data, summary, suggested_tags, new_dimensions
    """
    # Resolve model: per-type default > global default
    from app.config import get_model_defaults
    per_type = get_model_defaults().get("pdf-parse")
    if per_type and not _get_local_model_config(per_type):
        model = _get_model_for_override(per_type)
        eff_name = per_type
    else:
        model = _get_model()
        eff_name = _current_model_name or "unknown"
    if not model:
        return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                "extracted_info": {}}

    dimensions_desc = "\n".join(f"- {d['key']} ({d['label']}): 结构为 {d['schema']}" for d in dimensions)

    prompt = f"""你是一个简历解析助手。请仔细查看以下简历图片，提取结构化信息，填入人才卡片。

## 人才姓名: {talent_name or '从简历中识别'}

## 人才卡维度定义:
{dimensions_desc}

## 要求:
1. 仔细阅读简历图片中的所有内容（包括侧边栏、表格、图标旁文字等）
2. 从简历中提取信息，填入对应的维度
3. 如果能识别出姓名、邮箱、电话，请在返回的 extracted_info 中提供
4. 如果简历中有信息无法归入现有维度，建议新维度
5. 标签必须原子化，每个标签只表达一个独立概念，不要组合。例如"中科院硕士"应拆为"中科院"和"硕士"两个标签

请严格返回以下JSON格式（不要包含markdown代码块标记）:
{{
  "extracted_info": {{
    "name": "识别到的姓名",
    "email": "邮箱",
    "phone": "电话",
    "current_role": "当前职位",
    "department": "部门"
  }},
  "card_data": {{ ... 填充的卡片数据 ... }},
  "summary": "一句话描述",
  "suggested_tags": ["标签1"],
  "new_dimensions": []
}}
"""

    # Build multimodal content: prompt text + resume page images
    from PIL import Image as PILImage
    import io

    t0 = time.monotonic()
    content_parts = [prompt]

    if pdf_text_fallback and pdf_text_fallback.strip():
        content_parts.append(f"\n## 补充：文本提取结果（可能有乱码，仅供参考）:\n{pdf_text_fallback[:4000]}")

    for i, img_bytes in enumerate(pdf_images):
        img = PILImage.open(io.BytesIO(img_bytes))
        content_parts.append(img)
    logger.info(f"[TIMING] Image prep ({len(pdf_images)} pages): {time.monotonic() - t0:.2f}s")

    try:
        t1 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, content_parts)
        duration_ms = int((time.monotonic() - t1) * 1000)
        logger.info(f"[TIMING] Gemini pdf-parse API call: {duration_ms}ms")

        # Record usage
        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(eff_name, "pdf-parse", duration_ms, isl, osl)

        text = response.text.strip()
        result = _extract_json(text)
        if not isinstance(result, dict):
            logger.warning(f"LLM returned non-dict type: {type(result)}")
            return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                    "extracted_info": {}}
        return result
    except Exception as e:
        logger.error(f"LLM PDF parsing failed: {e}")
        return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                "extracted_info": {}}


async def parse_image_content(
    images: list[bytes],
    dimensions: list[dict],
    talent_name: str = "",
) -> dict:
    """Use VLM (multimodal) to extract structured info from uploaded images.

    Args:
        images: List of image bytes (PNG/JPG/etc.)
        dimensions: Card dimension definitions
        talent_name: Known talent name (optional)

    Returns: dict with extracted_info, card_data, summary, suggested_tags, new_dimensions
    """
    # Resolve model: per-type default > global default
    from app.config import get_model_defaults
    per_type = get_model_defaults().get("image-parse")
    if per_type and not _get_local_model_config(per_type):
        model = _get_model_for_override(per_type)
        eff_name = per_type
    else:
        model = _get_model()
        eff_name = _current_model_name or "unknown"
    if not model:
        return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                "extracted_info": {}}

    dimensions_desc = "\n".join(f"- {d['key']} ({d['label']}): 结构为 {d['schema']}" for d in dimensions)

    prompt = f"""你是一个人才信息提取助手。请仔细查看以下图片，提取与人才相关的结构化信息，填入人才卡片。
图片可能是名片、截图、证件照、简历照片等任何与人才相关的图片。

## 人才姓名: {talent_name or '从图片中识别'}

## 人才卡维度定义:
{dimensions_desc}

## 要求:
1. 仔细查看所有图片中的内容（包括文字、Logo、头像旁的信息等）
2. 从图片中提取信息，填入对应的维度
3. 如果能识别出姓名、邮箱、电话，请在返回的 extracted_info 中提供
4. 如果图片中有信息无法归入现有维度，建议新维度
5. 标签必须原子化，每个标签只表达一个独立概念，不要组合

请严格返回以下JSON格式（不要包含markdown代码块标记）:
{{
  "extracted_info": {{
    "name": "识别到的姓名",
    "email": "邮箱",
    "phone": "电话",
    "current_role": "当前职位",
    "department": "部门"
  }},
  "card_data": {{ ... 填充的卡片数据 ... }},
  "summary": "一句话描述",
  "suggested_tags": ["标签1"],
  "new_dimensions": []
}}
"""

    from PIL import Image as PILImage
    import io

    t0 = time.monotonic()
    content_parts = [prompt]

    for img_bytes in images:
        img = PILImage.open(io.BytesIO(img_bytes))
        content_parts.append(img)
    logger.info(f"[TIMING] Image prep ({len(images)} images): {time.monotonic() - t0:.2f}s")

    try:
        t1 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, content_parts)
        duration_ms = int((time.monotonic() - t1) * 1000)
        logger.info(f"[TIMING] Gemini image-parse API call: {duration_ms}ms")

        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(eff_name, "image-parse", duration_ms, isl, osl)

        text = response.text.strip()
        result = _extract_json(text)
        if not isinstance(result, dict):
            logger.warning(f"LLM returned non-dict type: {type(result)}")
            return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                    "extracted_info": {}}
        return result
    except Exception as e:
        logger.error(f"LLM image parsing failed: {e}")
        return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                "extracted_info": {}}


async def classify_idea(
    raw_text: str,
    existing_fragments: list[dict],
) -> dict:
    """Use LLM to classify, tag, and organize a new idea input.

    Returns: {
        "fragments": [
            {"action": "new"|"merge", "merge_target_id": int|null,
             "title": str, "content": str, "category": str, "tags": [str]}
        ]
    }
    """
    existing_desc = ""
    if existing_fragments:
        items = []
        for f in existing_fragments[:50]:
            items.append(f"ID={f['id']}, 标题={f['title']}, 分类={f['category']}, 标签={','.join(f.get('tags', []))}, 内容={f['content'][:100]}")
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

    try:
        text = await _call_model_text(prompt, call_type="idea-classify")
        if text is None:
            return {"fragments": [{"action": "new", "merge_target_id": None,
                                   "title": "未分类灵感", "content": raw_text,
                                   "category": "未分类", "tags": []}]}
        return _extract_json(text)
    except Exception as e:
        logger.error(f"LLM idea classification failed: {e}")
        return {"fragments": [{"action": "new", "merge_target_id": None,
                               "title": "未分类灵感", "content": raw_text,
                               "category": "未分类", "tags": []}]}


async def aggregate_idea_insights(
    fragments: list[dict],
    previous_liked_insights: list[str],
) -> list[dict]:
    """Aggregate all idea fragments into 1-3 deep insights.

    Returns: [{"content": str, "reasoning": str}, ...]
    """
    frag_text = "\n".join(
        f"- [{f['category']}] {f['title']}: {f['content'][:200]}"
        for f in fragments
    )

    liked_text = ""
    if previous_liked_insights:
        liked_text = "\n## 此前被认可的洞见（请参考但不要简单重复）:\n" + "\n".join(
            f"- {ins}" for ins in previous_liked_insights
        )

    prompt = f"""你是一个深度思考助手。以下是用户积累的所有灵感碎片。请你从这些碎片中，找出隐藏的联系、模式和深层含义，生成1到3条最有想象力、最深刻、最有价值的洞见和推论。

## 所有灵感碎片:
{frag_text[:8000]}
{liked_text}

## 要求:
1. 不要简单总结或复述碎片内容
2. 要发现碎片之间的深层联系，提炼出用户自己可能还没意识到的洞见
3. 每条洞见要有reasoning（推理过程）说明这个洞见是如何从碎片中推导出来的
4. 洞见要有启发性和行动指导意义
5. 生成1到3条，宁缺毋滥

请严格返回以下JSON格式（不要代码块）:
{{
  "insights": [
    {{
      "content": "洞见内容",
      "reasoning": "推理过程：从哪些碎片、如何推导出这个洞见"
    }}
  ]
}}"""

    try:
        text = await _call_model_text(prompt, call_type="idea-insight")
        if text is None:
            return []
        result = _extract_json(text)
        return result.get("insights", [])
    except Exception as e:
        logger.error(f"LLM idea insight aggregation failed: {e}")
        return []


async def semantic_search(
    query: str,
    all_talents_summary: list[dict],
) -> list[int]:
    """Use LLM to perform semantic search across talent summaries.

    Args:
        query: user's natural language query
        all_talents_summary: list of {"id": int, "name": str, "summary": str, "tags": list}

    Returns: list of talent IDs sorted by relevance
    """
    talents_text = "\n".join(
        f"ID={t['id']}, 姓名={t['name']}, 标签={','.join(t.get('tags', []))}, 摘要={t.get('summary', '无')}"
        for t in all_talents_summary
    )

    prompt = f"""你是一个人才搜索助手。用户在搜索人才信息，请根据用户的描述从人才列表中找出最匹配的人才。

## 用户搜索:
{query}

## 人才列表:
{talents_text[:6000]}

请返回匹配的人才ID列表，按相关度从高到低排序。只返回JSON数组格式（不要包含markdown代码块标记）:
[id1, id2, id3, ...]

如果没有匹配的人才，返回空数组: []
"""

    try:
        text = await _call_model_text(prompt, call_type="semantic-search")
        if text is None:
            return []
        return _extract_json(text)
    except Exception as e:
        logger.error(f"LLM semantic search failed: {e}")
        return []


async def analyze_query_dimensions(
    query: str,
    dimensions: list[dict],
    model_override: str | None = None,
) -> dict:
    """Step 1 of chat query: identify which dimensions are relevant to the user's question.

    Returns: {"relevant_dimensions": [{"key": str, "label": str}], "reasoning": str}
    """
    dimensions_desc = "\n".join(f"- {d['key']} ({d['label']}): 结构为 {d['schema']}" for d in dimensions)

    prompt = f"""你是一个人才数据分析助手。用户要查询关于人才库的问题，请判断回答这个问题需要查看哪些人才卡维度。

## 可用维度:
{dimensions_desc}

## 用户问题:
{query}

## 要求:
1. 选择与问题最相关的维度（可以多选）
2. 简要说明为什么选择这些维度

请严格返回以下JSON格式（不要包含markdown代码块标记）:
{{
  "relevant_dimensions": [{{"key": "dimension_key", "label": "维度中文名"}}, ...],
  "reasoning": "简要说明为什么选择这些维度"
}}
"""

    try:
        text = await _call_model_text(prompt, call_type="chat-analyze", model_override=model_override)
        if text is None:
            return {"relevant_dimensions": [], "reasoning": "模型未配置"}
        result = _extract_json(text)
        return {
            "relevant_dimensions": result.get("relevant_dimensions", []),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        logger.error(f"LLM chat-analyze failed: {e}")
        return {"relevant_dimensions": [], "reasoning": "分析失败"}


async def answer_talent_query(
    query: str,
    talents_context_json: str,
    dimensions_used: list[str],
    model_override: str | None = None,
) -> dict:
    """Step 2 of chat query: answer the user's question with talent data context.

    Returns: {"answer": str}
    """
    from datetime import datetime
    now_str = datetime.now().strftime("%Y年%m月%d日 %H:%M（%A）")

    prompt = f"""你是一个人才数据分析助手。请根据以下人才数据回答用户的问题。

## 当前时间:
{now_str}

## 人才数据（JSON格式，包含 {len(dimensions_used)} 个相关维度）:
{talents_context_json[:30000]}

## 用户问题:
{query}

## 要求:
1. 基于提供的数据如实回答，不要编造信息
2. 如果部分人才缺少回答所需的关键信息（如缺少生日日期、缺少某维度数据），请：
   a. 先从数据完整的人才中给出能回答的结果
   b. 再列出哪些人才缺少该关键信息，建议补充
3. 回答要简洁有条理
4. 如果涉及多个人才的对比，用列表展示
5. 不要简单说"无法回答"就结束，尽量从已有数据中挖掘有价值的信息

请直接回答（纯文本，不要JSON格式）:
"""

    try:
        text = await _call_model_text(prompt, call_type="chat-answer", model_override=model_override)
        if text is None:
            return {"answer": "模型未配置，无法回答"}
        return {"answer": text}
    except Exception as e:
        logger.error(f"LLM chat-answer failed: {e}")
        return {"answer": "回答生成失败，请重试"}
