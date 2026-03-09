import asyncio
import logging

import httpx

from app.config import get_notification_config

logger = logging.getLogger(__name__)

# Enterprise WeChat markdown content limit (bytes)
_WECOM_MAX_BYTES = 4096


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[: max_bytes - 6].decode("utf-8", errors="ignore")
    return truncated + "\n..."


async def send_wecom_webhook(webhook_url: str, title: str, content: str):
    md_body = f"## {title}\n{content}" if title else content
    md_body = _truncate_utf8(md_body, _WECOM_MAX_BYTES)
    payload = {"msgtype": "markdown", "markdown": {"content": md_body}}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errcode") != 0:
            logger.warning(f"WeCom webhook error: {data}")


async def send_notification(title: str, content: str):
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return

    channels = cfg.get("channels", {})

    # WeCom webhook
    wecom = channels.get("wecom_webhook", {})
    if wecom.get("enabled") and wecom.get("webhook_url"):
        try:
            await send_wecom_webhook(wecom["webhook_url"], title, content)
            logger.info(f"Notification sent via WeCom: {title}")
        except Exception as e:
            logger.error(f"WeCom notification failed: {e}")


def is_trigger_enabled(trigger_name: str) -> bool:
    cfg = get_notification_config()
    if not cfg.get("enabled"):
        return False
    return cfg.get("triggers", {}).get(trigger_name, False)


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
