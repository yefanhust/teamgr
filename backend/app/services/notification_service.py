import asyncio
import logging
from datetime import date

import httpx

from app.config import get_notification_config, get_notification_bots

logger = logging.getLogger(__name__)

# Enterprise WeChat markdown content limit (bytes)
_WECOM_MAX_BYTES = 4096


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[: max_bytes - 6].decode("utf-8", errors="ignore")
    return truncated + "\n..."


def _split_markdown_chunks(text: str, max_bytes: int) -> list[str]:
    """Split text into chunks that each fit within max_bytes (UTF-8).

    Tries to split at blank lines (paragraph boundaries) first,
    then falls back to single line boundaries.
    """
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    chunks = []
    current_lines: list[str] = []
    current_size = 0

    for line in text.split("\n"):
        line_bytes = len((line + "\n").encode("utf-8"))
        if current_size + line_bytes > max_bytes and current_lines:
            chunks.append("\n".join(current_lines))
            current_lines = []
            current_size = 0
        current_lines.append(line)
        current_size += line_bytes

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


async def _send_wecom_single(client: httpx.AsyncClient, webhook_url: str, md_body: str):
    payload = {"msgtype": "markdown", "markdown": {"content": md_body}}
    resp = await client.post(webhook_url, json=payload)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        logger.warning(f"WeCom webhook error: {data}")


async def send_wecom_webhook(webhook_url: str, title: str, content: str):
    # Reserve bytes for title in first chunk and continuation marker
    header = f"## {title}\n" if title else ""
    header_bytes = len(header.encode("utf-8"))

    chunks = _split_markdown_chunks(content, _WECOM_MAX_BYTES - header_bytes)

    async with httpx.AsyncClient(timeout=10) as client:
        for i, chunk in enumerate(chunks):
            if i == 0 and title:
                md_body = f"## {title}\n{chunk}"
            elif len(chunks) > 1:
                md_body = f"## {title}（续{i}）\n{chunk}" if title else chunk
            else:
                md_body = chunk
            md_body = _truncate_utf8(md_body, _WECOM_MAX_BYTES)
            await _send_wecom_single(client, webhook_url, md_body)


async def send_to_bot(bot: dict, title: str, content: str):
    """Send a message to a specific bot."""
    channel = bot.get("channel", "wecom")
    webhook_url = bot.get("webhook_url", "")
    if not webhook_url:
        return
    if channel == "wecom":
        await send_wecom_webhook(webhook_url, title, content)
        logger.info(f"Notification sent to bot '{bot.get('name', bot.get('id'))}': {title}")


async def send_notification(title: str, content: str):
    """Send to all enabled bots (backward compatible)."""
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return

    bots = get_notification_bots()
    for bot in bots:
        if not bot.get("enabled"):
            continue
        try:
            await send_to_bot(bot, title, content)
        except Exception as e:
            logger.error(f"Notification to bot '{bot.get('name')}' failed: {e}")


async def send_notification_for_trigger(trigger_name: str, title: str, content: str):
    """Send only to bots that have subscribed to this trigger."""
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return

    bots = get_notification_bots()
    for bot in bots:
        if not bot.get("enabled"):
            continue
        funcs = bot.get("functions", [])
        if any(f.get("trigger") == trigger_name for f in funcs):
            try:
                await send_to_bot(bot, title, content)
            except Exception as e:
                logger.error(f"Trigger notification '{trigger_name}' to bot '{bot.get('name')}' failed: {e}")


def is_trigger_enabled(trigger_name: str) -> bool:
    """Check if any bot has subscribed to this trigger."""
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return False
    bots = get_notification_bots()
    for bot in bots:
        if not bot.get("enabled"):
            continue
        funcs = bot.get("functions", [])
        if any(f.get("trigger") == trigger_name for f in funcs):
            return True
    return False


def send_notification_sync(title: str, content: str):
    if not get_notification_config().get("enabled"):
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(send_notification(title, content))
        else:
            loop.run_until_complete(send_notification(title, content))
    except RuntimeError:
        asyncio.run(send_notification(title, content))


def send_notification_for_trigger_sync(trigger_name: str, title: str, content: str):
    if not get_notification_config().get("enabled"):
        return
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(send_notification_for_trigger(trigger_name, title, content))
        else:
            loop.run_until_complete(send_notification_for_trigger(trigger_name, title, content))
    except RuntimeError:
        asyncio.run(send_notification_for_trigger(trigger_name, title, content))


# ---------------------------------------------------------------------------
# Content generators for each trigger type
# ---------------------------------------------------------------------------

def generate_deadline_content() -> tuple[str, str] | None:
    """Generate deadline reminder content. Returns (title, content) or None."""
    from app.database import SessionLocal
    from app.models.todo import TodoItem

    db = SessionLocal()
    try:
        today = date.today()
        items = (
            db.query(TodoItem)
            .filter(TodoItem.completed == False, TodoItem.deadline <= today)
            .order_by(TodoItem.deadline)
            .all()
        )
        if not items:
            return None

        overdue = [i for i in items if i.deadline < today]
        due_today = [i for i in items if i.deadline == today]

        lines = []
        if overdue:
            lines.append(f"**已逾期 ({len(overdue)})**")
            for item in overdue:
                lines.append(f"- {item.title}（截止 {item.deadline}）")
        if due_today:
            lines.append(f"**今日截止 ({len(due_today)})**")
            for item in due_today:
                time_str = f" {item.deadline_time}" if item.deadline_time else ""
                lines.append(f"- {item.title}{time_str}")

        return "任务截止提醒", "\n".join(lines)
    finally:
        db.close()


def generate_daily_list_content() -> tuple[str, str] | None:
    """Generate daily task list content. Returns (title, content) or None.
    Only includes regular TODO items, excludes vibe (研发) tasks.
    """
    from sqlalchemy import or_

    from app.database import SessionLocal
    from app.models.todo import TodoItem

    db = SessionLocal()
    try:
        today = date.today()
        items = (
            db.query(TodoItem)
            .filter(
                TodoItem.completed == False,
                or_(TodoItem.vibe_status.is_(None), TodoItem.vibe_status == ""),
            )
            .order_by(TodoItem.high_priority.desc(), TodoItem.deadline.asc().nullslast(), TodoItem.created_at.desc())
            .all()
        )
        if not items:
            return "每日任务清单", "当前没有待办任务"

        high_priority = [i for i in items if i.high_priority]
        due_today = [i for i in items if i.deadline == today and not i.high_priority]
        others = [i for i in items if not i.high_priority and i.deadline != today]

        lines = [f"共 **{len(items)}** 项待办\n"]

        if high_priority:
            lines.append(f"**高优先级 ({len(high_priority)})**")
            for item in high_priority:
                dl = f"（截止 {item.deadline}）" if item.deadline else ""
                lines.append(f"- {item.title}{dl}")

        if due_today:
            lines.append(f"\n**今日截止 ({len(due_today)})**")
            for item in due_today:
                time_str = f" {item.deadline_time}" if item.deadline_time else ""
                lines.append(f"- {item.title}{time_str}")

        if others:
            lines.append(f"\n**其他待办 ({len(others)})**")
            for item in others[:15]:
                dl = f"（截止 {item.deadline}）" if item.deadline else ""
                lines.append(f"- {item.title}{dl}")
            if len(others) > 15:
                lines.append(f"- ... 还有 {len(others) - 15} 项")

        return "每日任务清单", "\n".join(lines)
    finally:
        db.close()


def generate_trigger_content(trigger_name: str) -> tuple[str, str] | None:
    """Generate content for a given trigger. Returns (title, content) or None."""
    if trigger_name == "todo_deadline":
        return generate_deadline_content()
    elif trigger_name == "todo_daily_list":
        return generate_daily_list_content()
    elif trigger_name == "scheduled_query":
        return _fetch_latest_scheduled_query()
    elif trigger_name == "idea_insight":
        return _fetch_latest_idea_insight()
    elif trigger_name == "todo_analysis":
        return _fetch_latest_todo_analysis()
    elif trigger_name == "scholar_scheduled":
        return _fetch_latest_scholar_scheduled()
    return None


def _fetch_latest_scheduled_query() -> tuple[str, str] | None:
    from app.database import SessionLocal
    from app.models.talent import ScheduledQueryResult
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=1)
        results = (
            db.query(ScheduledQueryResult)
            .filter(ScheduledQueryResult.generated_at >= cutoff)
            .order_by(ScheduledQueryResult.generated_at.desc())
            .all()
        )
        if not results:
            return None
        summaries = []
        for r in results:
            summaries.append(f"**Q: {r.question_snapshot}**\n{r.answer}")
        content = "\n\n---\n\n".join(summaries)
        return "每日定时查询", content
    finally:
        db.close()


def _fetch_latest_idea_insight() -> tuple[str, str] | None:
    from app.database import SessionLocal
    from app.models.talent import IdeaInsight
    from datetime import datetime, timedelta, timezone

    db = SessionLocal()
    try:
        _CN_TZ = timezone(timedelta(hours=8))
        today = datetime.now(_CN_TZ).strftime("%Y-%m-%d")
        insights = (
            db.query(IdeaInsight)
            .filter(IdeaInsight.generated_date == today)
            .order_by(IdeaInsight.created_at.desc())
            .limit(5)
            .all()
        )
        if not insights:
            return None
        lines = []
        for ins in insights:
            if not ins.content:
                continue
            text = ins.content.strip()
            lines.append(text)
        content = "\n".join(f"- {line}" for line in lines if line)
        return "灵感洞见", content
    finally:
        db.close()


def _fetch_latest_scholar_scheduled() -> tuple[str, str] | None:
    """Fetch latest scholar scheduled results from today."""
    from app.database import SessionLocal
    from app.models.scholar import ScholarScheduledResult, ScholarScheduledQuestion
    from datetime import datetime, timedelta

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=1)
        results = (
            db.query(ScholarScheduledResult)
            .filter(
                ScholarScheduledResult.generated_at >= cutoff,
                ScholarScheduledResult.status == "success",
            )
            .order_by(ScholarScheduledResult.generated_at.desc())
            .all()
        )
        if not results:
            return None

        summaries = []
        for r in results:
            q = db.query(ScholarScheduledQuestion).filter(
                ScholarScheduledQuestion.id == r.question_id
            ).first()
            title = q.title if q else "定时问题"
            # Truncate long answers for notification
            answer = r.answer[:1500] if len(r.answer) > 1500 else r.answer
            summaries.append(f"**{title}** ({r.period_label})\n{answer}")

        content = "\n\n---\n\n".join(summaries)
        return "龙图阁定时报告", content
    finally:
        db.close()


def _fetch_latest_todo_analysis() -> tuple[str, str] | None:
    from app.database import SessionLocal
    from app.models.todo import TodoAnalysis

    db = SessionLocal()
    try:
        analysis = (
            db.query(TodoAnalysis)
            .order_by(TodoAnalysis.created_at.desc())
            .first()
        )
        if not analysis:
            return None
        return "任务效率分析", analysis.content
    finally:
        db.close()
