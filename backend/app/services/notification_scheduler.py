import logging
import os
from datetime import datetime, timedelta, timezone

from app.config import get_notification_bots
from app.services.notification_service import (
    generate_trigger_content,
    send_to_bot,
)

logger = logging.getLogger(__name__)

_NOTIF_JOB_PREFIX = "notif_"
_NOTIF_RECOVERY_PREFIX = "notif_recovery_"

_CN_TZ = timezone(timedelta(hours=8))
_DATA_DIR = os.environ.get("TEAMGR_DATA_DIR", "/app/data")
_SENT_DIR = os.path.join(_DATA_DIR, "notification-sent")
os.makedirs(_SENT_DIR, exist_ok=True)


def _sent_marker_path(bot_id: str, trigger: str, date_str: str) -> str:
    return os.path.join(_SENT_DIR, f"{bot_id}_{trigger}_{date_str}.sent")


def _mark_sent(bot_id: str, trigger: str):
    """Mark a trigger as sent for today (CN timezone)."""
    date_str = datetime.now(_CN_TZ).strftime("%Y-%m-%d")
    path = _sent_marker_path(bot_id, trigger, date_str)
    try:
        with open(path, "w") as f:
            f.write(datetime.now(_CN_TZ).isoformat())
    except OSError:
        pass


def _is_sent_today(bot_id: str, trigger: str) -> bool:
    """Check if a trigger has already been sent today."""
    date_str = datetime.now(_CN_TZ).strftime("%Y-%m-%d")
    return os.path.exists(_sent_marker_path(bot_id, trigger, date_str))


def _cleanup_old_markers():
    """Remove sent markers older than 3 days."""
    cutoff = (datetime.now(_CN_TZ) - timedelta(days=3)).strftime("%Y-%m-%d")
    try:
        for fname in os.listdir(_SENT_DIR):
            if not fname.endswith(".sent"):
                continue
            # Extract date from filename: botid_trigger_YYYY-MM-DD.sent
            parts = fname.rsplit("_", 1)
            if len(parts) == 2:
                date_part = parts[1].replace(".sent", "")
                if date_part < cutoff:
                    try:
                        os.remove(os.path.join(_SENT_DIR, fname))
                    except OSError:
                        pass
    except OSError:
        pass


def _make_delivery_job(bot: dict, trigger: str):
    """Create a closure that generates content and sends to a specific bot."""
    import asyncio

    bot_id = bot.get("id", "unknown")

    def job():
        result = generate_trigger_content(trigger)
        if result is None:
            logger.info(f"No content for trigger '{trigger}', skipping bot '{bot.get('name')}'")
            return
        title, content = result
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(send_to_bot(bot, title, content))
            else:
                loop.run_until_complete(send_to_bot(bot, title, content))
        except RuntimeError:
            asyncio.run(send_to_bot(bot, title, content))
        _mark_sent(bot_id, trigger)

    return job


def refresh_notification_jobs(scheduler):
    """Clear all notification delivery jobs, re-register based on current config."""
    if scheduler is None:
        return

    # Remove existing notification jobs
    for job in scheduler.get_jobs():
        if job.id.startswith(_NOTIF_JOB_PREFIX):
            scheduler.remove_job(job.id)
            logger.debug(f"Removed notification job: {job.id}")

    bots = get_notification_bots()
    count = 0
    for bot in bots:
        if not bot.get("enabled"):
            continue
        bot_id = bot.get("id", "unknown")
        for func in bot.get("functions", []):
            trigger = func.get("trigger")
            cron_hour = func.get("cron_hour", 8)
            cron_minute = func.get("cron_minute", 0)
            job_id = f"{_NOTIF_JOB_PREFIX}{bot_id}_{trigger}"

            scheduler.add_job(
                _make_delivery_job(bot, trigger),
                "cron",
                hour=cron_hour,
                minute=cron_minute,
                id=job_id,
                replace_existing=True,
            )
            logger.info(
                f"Notification job registered: bot='{bot.get('name')}' "
                f"trigger='{trigger}' at {cron_hour:02d}:{cron_minute:02d}"
            )
            count += 1

    logger.info(f"Notification scheduler refreshed: {count} job(s) registered")


def check_missed_notifications(scheduler):
    """On startup, detect notification triggers that missed their scheduled time
    today and schedule immediate recovery deliveries.

    Uses file-based markers to avoid duplicate sends across restarts.
    """
    if scheduler is None:
        return

    _cleanup_old_markers()

    now = datetime.now(_CN_TZ)
    bots = get_notification_bots()
    recovery_count = 0

    for bot in bots:
        if not bot.get("enabled"):
            continue
        bot_id = bot.get("id", "unknown")

        for func in bot.get("functions", []):
            trigger = func.get("trigger")
            cron_hour = func.get("cron_hour", 8)
            cron_minute = func.get("cron_minute", 0)

            # Only recover if the scheduled time has passed today
            scheduled_time = now.replace(
                hour=cron_hour, minute=cron_minute, second=0, microsecond=0
            )
            if now < scheduled_time:
                continue

            # Skip if already sent today
            if _is_sent_today(bot_id, trigger):
                continue

            # Schedule recovery with staggered delay
            delay_seconds = 30 + recovery_count * 15
            run_at = datetime.now() + timedelta(seconds=delay_seconds)
            job_id = f"{_NOTIF_RECOVERY_PREFIX}{bot_id}_{trigger}"

            scheduler.add_job(
                _make_delivery_job(bot, trigger),
                "date",
                run_date=run_at,
                id=job_id,
                replace_existing=True,
            )
            recovery_count += 1
            logger.info(
                f"Missed notification detected: bot='{bot.get('name')}' "
                f"trigger='{trigger}' (was {cron_hour:02d}:{cron_minute:02d}), "
                f"recovery in {delay_seconds}s"
            )

    if recovery_count:
        logger.info(f"Notification recovery: {recovery_count} missed delivery(s) scheduled")
    else:
        logger.info("Notification recovery: no missed deliveries detected")
