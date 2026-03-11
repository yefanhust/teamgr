"""Scholar (龙图阁大学士) service — signal file writing + stream file reading."""

import asyncio
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_DATA_DIR = os.environ.get("TEAMGR_DATA_DIR", "/app/data")
_QUEUE_DIR = os.path.join(_DATA_DIR, "scholar-queue")
_STREAM_DIR = os.path.join(_DATA_DIR, "scholar-stream")
_FILES_DIR = os.path.join(_DATA_DIR, "scholar-files")
_SESSIONS_DIR = os.path.join(_DATA_DIR, "scholar-sessions")
_CONVERSATIONS_FILE = os.path.join(_DATA_DIR, "scholar-conversations.json")

# Ensure dirs exist
for _d in (_QUEUE_DIR, _STREAM_DIR, _FILES_DIR, _SESSIONS_DIR):
    os.makedirs(_d, exist_ok=True)

# Max text characters to inject into prompt from PDFs
_MAX_FILE_TEXT_CHARS = 80_000
_STREAM_POLL_INTERVAL = 0.2  # seconds
_STREAM_TIMEOUT = 300  # 5 minutes


def gen_id() -> str:
    return uuid.uuid4().hex[:12]


# ──────────────── File upload ────────────────


def save_uploaded_file(filename: str, content: bytes) -> dict:
    """Save uploaded file and extract text. Returns file metadata."""
    from app.services.pdf_service import extract_text_from_pdf

    file_id = gen_id()
    file_dir = os.path.join(_FILES_DIR, file_id)
    os.makedirs(file_dir, exist_ok=True)

    # Save original
    ext = os.path.splitext(filename)[1].lower()
    orig_path = os.path.join(file_dir, f"original{ext}")
    with open(orig_path, "wb") as f:
        f.write(content)

    # Extract text
    text = ""
    page_count = 0
    if ext == ".pdf":
        try:
            text = extract_text_from_pdf(content)
            import pdfplumber, io
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                page_count = len(pdf.pages)
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
            text = f"[PDF文本提取失败: {e}]"
    elif ext in (".txt", ".md", ".csv", ".json", ".yaml", ".yml"):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = "[文本解码失败]"
    else:
        text = f"[不支持的文件类型: {ext}]"

    # Save extracted text
    text_path = os.path.join(file_dir, "extracted.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)

    preview = text[:500].strip() if text else ""

    return {
        "file_id": file_id,
        "filename": filename,
        "page_count": page_count,
        "text_preview": preview,
    }


def get_file_text(file_id: str) -> str:
    """Load extracted text for a file."""
    text_path = os.path.join(_FILES_DIR, file_id, "extracted.txt")
    if not os.path.exists(text_path):
        return ""
    with open(text_path, "r", encoding="utf-8") as f:
        return f.read()


# ──────────────── Conversation management ────────────────


def _load_conversations() -> list[dict]:
    if not os.path.exists(_CONVERSATIONS_FILE):
        return []
    try:
        with open(_CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_conversations(convs: list[dict]):
    with open(_CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(convs, f, ensure_ascii=False, indent=2)


def get_conversation_session_id(conversation_id: str) -> str:
    """Get the Claude session ID for a conversation."""
    path = os.path.join(_SESSIONS_DIR, conversation_id)
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read().strip()
    return ""


def list_conversations() -> list[dict]:
    convs = _load_conversations()
    # Return newest first, without full messages
    result = []
    for c in reversed(convs):
        result.append({
            "conversation_id": c["conversation_id"],
            "title": c.get("title", ""),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
            "message_count": len(c.get("messages", [])),
        })
    return result


_CATEGORY_CACHE_FILE = os.path.join(_DATA_DIR, "scholar-category-cache.json")


def _conv_fingerprint(convs: list[dict]) -> str:
    """Hash of conversation IDs to detect list changes."""
    ids = sorted(c["conversation_id"] for c in convs)
    return hashlib.md5("|".join(ids).encode()).hexdigest()


def _load_category_cache() -> dict | None:
    """Load cached categorization result. Returns {"fingerprint": str, "categories": list} or None."""
    try:
        if os.path.exists(_CATEGORY_CACHE_FILE):
            with open(_CATEGORY_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_category_cache(fingerprint: str, categories: list[dict]):
    """Save categorization result to cache."""
    try:
        with open(_CATEGORY_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fingerprint, "categories": categories}, f, ensure_ascii=False)
    except OSError as e:
        logger.warning(f"Failed to save category cache: {e}")


def _rebuild_cached_categories(cached_categories: list[dict], convs: list[dict]) -> list[dict]:
    """Rebuild category results with fresh conversation metadata (message_count, updated_at, etc.)."""
    conv_map = {}
    for c in convs:
        conv_map[c["conversation_id"]] = {
            "conversation_id": c["conversation_id"],
            "title": c.get("title", ""),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
            "message_count": len(c.get("messages", [])),
        }

    result = []
    for cat in cached_categories:
        items = []
        for conv in cat.get("conversations", []):
            cid = conv.get("conversation_id", "")
            if cid in conv_map:
                items.append(conv_map[cid])
        if items:
            items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            result.append({"category": cat["category"], "conversations": items})
    return result


async def categorize_conversations() -> list[dict]:
    """Use LLM to categorize conversations by topic. Cached until conversation list changes."""
    convs = _load_conversations()
    if not convs:
        return []

    fingerprint = _conv_fingerprint(convs)

    # Check cache
    cache = _load_category_cache()
    if cache and cache.get("fingerprint") == fingerprint:
        logger.info("Scholar categorization: using cache")
        return _rebuild_cached_categories(cache["categories"], convs)

    # Build a summary of conversations for the LLM
    conv_summaries = []
    for c in convs:
        titles_and_questions = [c.get("title", "")]
        for msg in c.get("messages", [])[:3]:  # first 3 questions
            q = msg.get("question", "")
            if q and q != c.get("title", ""):
                titles_and_questions.append(q[:80])
        conv_summaries.append({
            "id": c["conversation_id"],
            "content": " | ".join(titles_and_questions),
        })

    # Build prompt
    conv_list = "\n".join(
        f'{i+1}. [{s["id"]}] {s["content"]}'
        for i, s in enumerate(conv_summaries)
    )
    prompt = f"""请将以下对话按主题分类。每个分类包含一个简短的中文类别名（2-4个字）。
一个对话只能属于一个分类。分类数量控制在2-6个。如果只有少量对话，可以只分1-2类。

对话列表:
{conv_list}

请直接输出JSON数组，格式如下（不要输出其他内容）:
[
  {{"category": "分类名", "conversation_ids": ["id1", "id2"]}}
]"""

    try:
        from app.services.llm_service import _call_model_text, _extract_json
        result = await _call_model_text(prompt, call_type="scholar-categorize")
        if not result:
            return _fallback_categories(convs)

        parsed = _extract_json(result)
        if not isinstance(parsed, list):
            return _fallback_categories(convs)

        # Build lookup for conversation details
        conv_map = {}
        for c in convs:
            conv_map[c["conversation_id"]] = {
                "conversation_id": c["conversation_id"],
                "title": c.get("title", ""),
                "created_at": c.get("created_at", ""),
                "updated_at": c.get("updated_at", ""),
                "message_count": len(c.get("messages", [])),
            }

        # Build categorized result
        assigned = set()
        categories = []
        for cat in parsed:
            name = cat.get("category", "其他")
            ids = cat.get("conversation_ids", [])
            items = []
            for cid in ids:
                if cid in conv_map and cid not in assigned:
                    items.append(conv_map[cid])
                    assigned.add(cid)
            if items:
                # Sort items within category by updated_at descending
                items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
                categories.append({"category": name, "conversations": items})

        # Add uncategorized conversations
        uncategorized = [
            conv_map[c["conversation_id"]]
            for c in convs
            if c["conversation_id"] not in assigned
        ]
        if uncategorized:
            uncategorized.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            categories.append({"category": "其他", "conversations": uncategorized})

        # Save to cache
        _save_category_cache(fingerprint, categories)
        logger.info(f"Scholar categorization: LLM called, {len(categories)} categories cached")

        return categories

    except Exception as e:
        logger.error(f"Conversation categorization failed: {e}")
        return _fallback_categories(convs)


def _fallback_categories(convs: list[dict]) -> list[dict]:
    """Fallback: return all conversations in a single '全部' category."""
    items = []
    for c in reversed(convs):
        items.append({
            "conversation_id": c["conversation_id"],
            "title": c.get("title", ""),
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
            "message_count": len(c.get("messages", [])),
        })
    return [{"category": "全部", "conversations": items}]


def get_conversation(conversation_id: str) -> dict | None:
    convs = _load_conversations()
    for c in convs:
        if c["conversation_id"] == conversation_id:
            return c
    return None


def create_or_update_conversation(
    conversation_id: str,
    query_id: str,
    question: str,
    file_ids: list[str] = None,
) -> dict:
    """Create a new conversation or add a message to an existing one."""
    convs = _load_conversations()
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()

    existing = None
    for c in convs:
        if c["conversation_id"] == conversation_id:
            existing = c
            break

    msg = {
        "query_id": query_id,
        "question": question,
        "answer": "",
        "file_ids": file_ids or [],
        "timestamp": now,
    }

    if existing:
        existing["messages"].append(msg)
        existing["updated_at"] = now
    else:
        existing = {
            "conversation_id": conversation_id,
            "title": question[:50],
            "created_at": now,
            "updated_at": now,
            "messages": [msg],
        }
        convs.append(existing)

    _save_conversations(convs)
    return existing


def delete_conversation(conversation_id: str) -> bool:
    convs = _load_conversations()
    original_len = len(convs)
    convs = [c for c in convs if c["conversation_id"] != conversation_id]
    if len(convs) < original_len:
        _save_conversations(convs)
        # Also remove session file
        session_path = os.path.join(_SESSIONS_DIR, conversation_id)
        if os.path.exists(session_path):
            os.remove(session_path)
        return True
    return False


def find_conversation_id_by_query(query_id: str) -> str:
    """Find the conversation_id that contains a given query_id."""
    convs = _load_conversations()
    for c in convs:
        for msg in c.get("messages", []):
            if msg["query_id"] == query_id:
                return c["conversation_id"]
    return ""


def update_conversation_answer(conversation_id: str, query_id: str, answer: str):
    """Save the assistant's answer to the conversation record."""
    convs = _load_conversations()
    for c in convs:
        if c["conversation_id"] == conversation_id:
            for msg in c.get("messages", []):
                if msg["query_id"] == query_id:
                    msg["answer"] = answer
                    _save_conversations(convs)
                    logger.info(f"Saved answer for query {query_id} ({len(answer)} chars)")
                    return
    logger.warning(f"Could not find conversation/query to save answer: {conversation_id}/{query_id}")


# ──────────────── Signal file writing ────────────────


def write_query_signal(
    query_id: str,
    question: str,
    conversation_id: str,
    session_id: str = "",
    file_ids: list[str] = None,
):
    """Write a signal file for scholar-watcher to pick up."""
    # Gather file texts
    context_parts = []
    for fid in (file_ids or []):
        text = get_file_text(fid)
        if text:
            # Get filename from metadata
            file_dir = os.path.join(_FILES_DIR, fid)
            orig_files = [f for f in os.listdir(file_dir) if f.startswith("original")]
            fname = orig_files[0] if orig_files else fid
            context_parts.append(f"[文件: {fname}]\n{text}")

    context = "\n\n---\n\n".join(context_parts)
    if len(context) > _MAX_FILE_TEXT_CHARS:
        context = context[:_MAX_FILE_TEXT_CHARS] + "\n\n[... 文档内容过长，已截断 ...]"

    signal = {
        "query_id": query_id,
        "conversation_id": conversation_id,
        "session_id": session_id,
        "prompt": question,
        "context": context,
        "timestamp": int(datetime.now().timestamp()),
    }

    signal_path = os.path.join(_QUEUE_DIR, f"{query_id}.json")
    with open(signal_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False)

    logger.info(f"Scholar query signal written: {query_id} (conv={conversation_id[:8]})")


# ──────────────── Stream file reading (SSE) ────────────────


def _parse_stream_event(line: str) -> list[dict] | None:
    """Parse a stream-json line from Claude CLI into frontend-friendly events."""
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None

    etype = event.get("type", "")

    if etype == "system":
        subtype = event.get("subtype", "")
        if subtype == "init":
            return [{"type": "init", "model": event.get("model", "")}]
        return None

    if etype == "assistant":
        msg = event.get("message", {})
        if isinstance(msg, str):
            try:
                msg = json.loads(msg)
            except (json.JSONDecodeError, ValueError):
                return None
        content = msg.get("content", [])
        if not content:
            return None

        results = []
        for block in content:
            bt = block.get("type", "")
            if bt == "thinking":
                results.append({
                    "type": "thinking",
                    "content": block.get("thinking", ""),
                })
            elif bt == "text":
                text = block.get("text", "")
                if text:
                    results.append({"type": "text", "content": text})
            elif bt == "tool_use":
                results.append({
                    "type": "tool_use",
                    "tool": block.get("name", ""),
                    "input": block.get("input", {}),
                })
        return results if results else None

    if etype == "result":
        return [{
            "type": "done",
            "result": event.get("result", ""),
            "session_id": event.get("session_id", "")
                          or event.get("sessionId", ""),
            "duration_ms": event.get("duration_ms"),
            "cost_usd": event.get("cost_usd"),
        }]

    return None


async def stream_response(query_id: str, conversation_id: str = ""):
    """Async generator: tail the stream file and yield SSE events.

    Yields strings in SSE format: "data: {...}\\n\\n"
    Also accumulates assistant text and saves it to the conversation when done.
    """
    stream_file = os.path.join(_STREAM_DIR, f"{query_id}.jsonl")
    done_file = os.path.join(_STREAM_DIR, f"{query_id}.done")

    pos = 0  # byte offset for binary reads
    elapsed = 0.0
    accumulated_text = []  # collect assistant text chunks

    def _read_new_lines() -> list[str]:
        """Read new lines from stream file starting at byte pos. Returns lines, updates pos."""
        nonlocal pos
        lines = []
        try:
            with open(stream_file, "rb") as f:
                f.seek(pos)
                new_data = f.read()
                if new_data:
                    pos += len(new_data)
                    text = new_data.decode("utf-8", errors="replace")
                    for line in text.split("\n"):
                        line = line.strip()
                        if line:
                            lines.append(line)
        except OSError:
            pass
        return lines

    def _lines_to_sse(lines: list[str]):
        """Parse lines and yield SSE events. Returns list of SSE strings and whether done."""
        results = []
        done = False
        for line in lines:
            events = _parse_stream_event(line)
            if events:
                for evt in events:
                    results.append(f"data: {json.dumps(evt, ensure_ascii=False)}\n\n")
                    if evt["type"] == "text":
                        accumulated_text.append(evt.get("content", ""))
                    elif evt["type"] == "done":
                        done = True
                        # Save result text if available
                        if evt.get("result"):
                            accumulated_text.append(evt["result"])
        return results, done

    def _save_answer():
        """Save accumulated answer to the conversation record."""
        if conversation_id and accumulated_text:
            answer = "".join(accumulated_text)
            if answer.strip():
                update_conversation_answer(conversation_id, query_id, answer)

    while elapsed < _STREAM_TIMEOUT:
        if os.path.exists(stream_file):
            lines = _read_new_lines()
            if lines:
                sse_events, is_done = _lines_to_sse(lines)
                for sse in sse_events:
                    yield sse
                if is_done:
                    _save_answer()
                    return

        if os.path.exists(done_file):
            # Final drain
            if os.path.exists(stream_file):
                lines = _read_new_lines()
                if lines:
                    sse_events, _ = _lines_to_sse(lines)
                    for sse in sse_events:
                        yield sse
            yield f"data: {json.dumps({'type': 'done', 'result': '', 'session_id': ''}, ensure_ascii=False)}\n\n"
            _save_answer()
            return

        await asyncio.sleep(_STREAM_POLL_INTERVAL)
        elapsed += _STREAM_POLL_INTERVAL

    # Timeout
    _save_answer()
    yield f"data: {json.dumps({'type': 'error', 'content': '响应超时，请重试'}, ensure_ascii=False)}\n\n"
