import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import (
    get_notification_bots,
    save_notification_bots,
    TRIGGER_TYPES,
)
from app.services.notification_service import (
    generate_trigger_content,
    send_to_bot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notification", tags=["notification"])


def _mask_webhook_url(url: str) -> str:
    """Mask the key parameter in webhook URL for security."""
    if "key=" in url:
        parts = url.split("key=", 1)
        key = parts[1].split("&")[0] if "&" in parts[1] else parts[1]
        if len(key) > 4:
            masked = key[:4] + "****"
        else:
            masked = "****"
        return url.replace(key, masked)
    return url


def _bot_response(bot: dict) -> dict:
    """Return bot dict with masked webhook URL."""
    return {
        **bot,
        "webhook_url_masked": _mask_webhook_url(bot.get("webhook_url", "")),
    }


def _get_scheduler():
    """Get the global scheduler instance from main."""
    from app.main import _scheduler
    return _scheduler


# ---- Trigger Types ----

@router.get("/trigger-types")
def get_trigger_types():
    return {"trigger_types": TRIGGER_TYPES}


# ---- Bot CRUD ----

@router.get("/bots")
def list_bots():
    bots = get_notification_bots()
    return {"bots": [_bot_response(b) for b in bots]}


class BotCreate(BaseModel):
    name: str
    channel: str = "wecom"
    webhook_url: str


@router.post("/bots")
def create_bot(body: BotCreate):
    bots = get_notification_bots()
    bot_id = uuid.uuid4().hex[:8]
    new_bot = {
        "id": bot_id,
        "name": body.name,
        "channel": body.channel,
        "webhook_url": body.webhook_url,
        "enabled": True,
        "functions": [],
    }
    bots.append(new_bot)
    save_notification_bots(bots)
    _refresh_scheduler()
    return _bot_response(new_bot)


class BotUpdate(BaseModel):
    name: str | None = None
    webhook_url: str | None = None
    enabled: bool | None = None


@router.put("/bots/{bot_id}")
def update_bot(bot_id: str, body: BotUpdate):
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    if body.name is not None:
        bot["name"] = body.name
    if body.webhook_url is not None:
        bot["webhook_url"] = body.webhook_url
    if body.enabled is not None:
        bot["enabled"] = body.enabled
    save_notification_bots(bots)
    _refresh_scheduler()
    return _bot_response(bot)


@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: str):
    bots = get_notification_bots()
    _find_bot(bots, bot_id)  # validate exists
    bots = [b for b in bots if b.get("id") != bot_id]
    save_notification_bots(bots)
    _refresh_scheduler()
    return {"ok": True}


# ---- Bot Functions (trigger subscriptions) ----

class FunctionAdd(BaseModel):
    trigger: str
    cron_hour: int = 8
    cron_minute: int = 0


@router.post("/bots/{bot_id}/functions")
def add_function(bot_id: str, body: FunctionAdd):
    if body.trigger not in TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown trigger: {body.trigger}")
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    funcs = bot.setdefault("functions", [])
    # Check duplicate
    if any(f.get("trigger") == body.trigger for f in funcs):
        raise HTTPException(status_code=400, detail=f"Trigger '{body.trigger}' already added")
    funcs.append({
        "trigger": body.trigger,
        "cron_hour": body.cron_hour,
        "cron_minute": body.cron_minute,
    })
    save_notification_bots(bots)
    _refresh_scheduler()
    return _bot_response(bot)


class FunctionUpdate(BaseModel):
    cron_hour: int
    cron_minute: int


@router.put("/bots/{bot_id}/functions/{trigger}")
def update_function(bot_id: str, trigger: str, body: FunctionUpdate):
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    func = _find_function(bot, trigger)
    func["cron_hour"] = body.cron_hour
    func["cron_minute"] = body.cron_minute
    save_notification_bots(bots)
    _refresh_scheduler()
    return _bot_response(bot)


@router.delete("/bots/{bot_id}/functions/{trigger}")
def delete_function(bot_id: str, trigger: str):
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    _find_function(bot, trigger)  # validate exists
    bot["functions"] = [f for f in bot.get("functions", []) if f.get("trigger") != trigger]
    save_notification_bots(bots)
    _refresh_scheduler()
    return _bot_response(bot)


# ---- Send / Test ----

class SendMessage(BaseModel):
    content: str


@router.post("/bots/{bot_id}/send")
async def send_custom_message(bot_id: str, body: SendMessage):
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Message content is empty")
    try:
        await send_to_bot(bot, "", body.content)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/test/{trigger}")
async def test_trigger(bot_id: str, trigger: str):
    if trigger not in TRIGGER_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown trigger: {trigger}")
    bots = get_notification_bots()
    bot = _find_bot(bots, bot_id)
    result = generate_trigger_content(trigger)
    if result is None:
        raise HTTPException(status_code=404, detail="No content available for this trigger")
    title, content = result
    try:
        await send_to_bot(bot, title, content)
        return {"ok": True, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Helpers ----

def _find_bot(bots: list, bot_id: str) -> dict:
    for b in bots:
        if b.get("id") == bot_id:
            return b
    raise HTTPException(status_code=404, detail=f"Bot not found: {bot_id}")


def _find_function(bot: dict, trigger: str) -> dict:
    for f in bot.get("functions", []):
        if f.get("trigger") == trigger:
            return f
    raise HTTPException(status_code=404, detail=f"Function not found: {trigger}")


def _refresh_scheduler():
    scheduler = _get_scheduler()
    if scheduler:
        from app.services.notification_scheduler import refresh_notification_jobs
        refresh_notification_jobs(scheduler)
