import asyncio
import json
import logging
import time
from typing import Optional

import google.generativeai as genai
from app.config import get_gemini_config

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


def _get_model():
    global _model_instance, _current_model_name
    cfg = get_gemini_config()
    api_key = cfg.get("api_key", "")
    model_name = cfg.get("current_model", "gemini-3-flash-preview")

    if not api_key or api_key == "your-gemini-api-key-here":
        logger.warning("Gemini API key not configured. LLM features will not work.")
        return None

    if _model_instance is None or _current_model_name != model_name:
        genai.configure(api_key=api_key)
        _model_instance = genai.GenerativeModel(model_name)
        _current_model_name = model_name
        logger.info(f"Gemini model initialized: {model_name}")

    return _model_instance


def get_current_model_name() -> str:
    cfg = get_gemini_config()
    return cfg.get("current_model", "gemini-2.5-flash")


def get_available_models() -> list:
    cfg = get_gemini_config()
    return cfg.get(
        "available_models",
        [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
        ],
    )


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
    model = _get_model()
    if not model:
        return {
            "card_data": existing_card_data,
            "summary": "",
            "suggested_tags": [],
            "new_dimensions": [],
        }

    dimensions_desc = "\n".join(f"- {d['key']} ({d['label']}): 结构为 {d['schema']}" for d in dimensions)

    prompt = f"""你是一个人才信息整理助手。请根据用户输入的信息，更新人才卡片数据。

## 当前人才: {talent_name or '未命名'}

## 当前维度定义:
{dimensions_desc}

## 当前卡片数据:
```json
{json.dumps(existing_card_data, ensure_ascii=False, indent=2)}
```

## 用户新输入的信息:
{user_input}

## 要求:
1. 将用户输入的信息整理并合并到对应的维度中
2. 保留已有的信息，新增或更新相关字段
3. 如果用户输入的信息无法归入现有维度，可以在 new_dimensions 中建议新增维度
4. 为此人才建议合适的标签。标签必须原子化，每个标签只表达一个独立概念，不要组合。例如"中科院硕士"应拆为"中科院"和"硕士"两个标签，"前端技术专家"应拆为"前端"和"技术专家"
5. 生成一句话总结更新到 one_liner 维度

请严格返回以下JSON格式（不要包含markdown代码块标记）:
{{
  "card_data": {{ ... 更新后的完整卡片数据，key必须与维度定义对齐 ... }},
  "summary": "一句话描述这个人才",
  "suggested_tags": ["标签1", "标签2"],
  "new_dimensions": [
    {{
      "key": "dimension_key",
      "label": "维度中文名",
      "schema": "JSON schema string defining the structure"
    }}
  ]
}}
"""

    try:
        t0 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, prompt)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Gemini text-entry API call: {duration_ms}ms")

        # Record usage
        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(_current_model_name or "unknown", "text-entry", duration_ms, isl, osl)

        text = response.text.strip()
        # Try to extract JSON if wrapped in code blocks
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.startswith("```") and not inside:
                    inside = True
                    continue
                elif line.startswith("```") and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        result = json.loads(text)
        return {
            "card_data": result.get("card_data", existing_card_data),
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
    model = _get_model()
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
        _record_llm_usage(_current_model_name or "unknown", "pdf-parse", duration_ms, isl, osl)

        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.startswith("```") and not inside:
                    inside = True
                    continue
                elif line.startswith("```") and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        result = json.loads(text)
        # Ensure result is a dict
        if not isinstance(result, dict):
            logger.warning(f"LLM returned non-dict type: {type(result)}")
            return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                    "extracted_info": {}}
        return result
    except Exception as e:
        logger.error(f"LLM PDF parsing failed: {e}")
        return {"card_data": {}, "summary": "", "suggested_tags": [], "new_dimensions": [],
                "extracted_info": {}}


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
    model = _get_model()
    if not model:
        return []

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
        t0 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, prompt)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Gemini semantic-search API call: {duration_ms}ms")

        # Record usage
        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(_current_model_name or "unknown", "semantic-search", duration_ms, isl, osl)

        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.startswith("```") and not inside:
                    inside = True
                    continue
                elif line.startswith("```") and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)
        return json.loads(text)
    except Exception as e:
        logger.error(f"LLM semantic search failed: {e}")
        return []


async def analyze_query_dimensions(
    query: str,
    dimensions: list[dict],
) -> dict:
    """Step 1 of chat query: identify which dimensions are relevant to the user's question.

    Returns: {"relevant_dimensions": [{"key": str, "label": str}], "reasoning": str}
    """
    model = _get_model()
    if not model:
        return {"relevant_dimensions": [], "reasoning": "模型未配置"}

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
        t0 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, prompt)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Gemini chat-analyze API call: {duration_ms}ms")

        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(_current_model_name or "unknown", "chat-analyze", duration_ms, isl, osl)

        text = response.text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            inside = False
            for line in lines:
                if line.startswith("```") and not inside:
                    inside = True
                    continue
                elif line.startswith("```") and inside:
                    break
                elif inside:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        result = json.loads(text)
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
) -> dict:
    """Step 2 of chat query: answer the user's question with talent data context.

    Returns: {"answer": str}
    """
    model = _get_model()
    if not model:
        return {"answer": "模型未配置，无法回答"}

    prompt = f"""你是一个人才数据分析助手。请根据以下人才数据回答用户的问题。

## 人才数据（JSON格式，包含 {len(dimensions_used)} 个相关维度）:
{talents_context_json[:30000]}

## 用户问题:
{query}

## 要求:
1. 基于提供的数据如实回答，不要编造信息
2. 如果数据不足以回答，请说明
3. 回答要简洁有条理
4. 如果涉及多个人才的对比，用列表展示

请直接回答（纯文本，不要JSON格式）:
"""

    try:
        t0 = time.monotonic()
        response = await asyncio.to_thread(model.generate_content, prompt)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(f"[TIMING] Gemini chat-answer API call: {duration_ms}ms")

        usage = getattr(response, 'usage_metadata', None)
        isl = getattr(usage, 'prompt_token_count', 0) or 0
        osl = getattr(usage, 'candidates_token_count', 0) or 0
        _record_llm_usage(_current_model_name or "unknown", "chat-answer", duration_ms, isl, osl)

        return {"answer": response.text.strip()}
    except Exception as e:
        logger.error(f"LLM chat-answer failed: {e}")
        return {"answer": "回答生成失败，请重试"}
