import logging

from app.config import get_notification_bots
from app.services.notification_service import (
    generate_trigger_content,
    send_to_bot,
)

logger = logging.getLogger(__name__)

_NOTIF_JOB_PREFIX = "notif_"


def _make_delivery_job(bot: dict, trigger: str):
    """Create a closure that generates content and sends to a specific bot."""
    import asyncio

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
