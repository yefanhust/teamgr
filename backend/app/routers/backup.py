import logging
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import desc

from app.database import SessionLocal
from app.models.backup import BackupLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/logs")
def get_backup_logs(limit: int = 30):
    """Get recent backup logs."""
    db = SessionLocal()
    try:
        logs = (
            db.query(BackupLog)
            .order_by(desc(BackupLog.created_at))
            .limit(limit)
            .all()
        )
        return [
            {
                "id": log.id,
                "status": log.status,
                "file_size": log.file_size,
                "cos_key": log.cos_key,
                "error_message": log.error_message,
                "encrypted": log.encrypted,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    finally:
        db.close()


@router.get("/status")
def get_backup_status():
    """Get backup health status for the navbar badge."""
    db = SessionLocal()
    try:
        last_log = (
            db.query(BackupLog)
            .order_by(desc(BackupLog.created_at))
            .first()
        )
        last_success = (
            db.query(BackupLog)
            .filter(BackupLog.status == "success")
            .order_by(desc(BackupLog.created_at))
            .first()
        )

        now = datetime.utcnow()
        healthy = True
        reason = ""

        if last_log is None:
            # No backup logs at all — may be first run
            healthy = True
            reason = "no_logs"
        elif last_log.status == "failed":
            healthy = False
            reason = "last_failed"
        elif last_success and last_success.completed_at:
            hours_since = (now - last_success.completed_at).total_seconds() / 3600
            if hours_since > 36:
                healthy = False
                reason = "stale"

        return {
            "healthy": healthy,
            "reason": reason,
            "last_backup": {
                "status": last_log.status if last_log else None,
                "file_size": last_log.file_size if last_log else None,
                "encrypted": last_log.encrypted if last_log else None,
                "completed_at": last_log.completed_at.isoformat() if last_log and last_log.completed_at else None,
                "error_message": last_log.error_message if last_log else None,
            },
            "last_success_at": last_success.completed_at.isoformat() if last_success and last_success.completed_at else None,
        }
    finally:
        db.close()


@router.post("/trigger")
def trigger_backup():
    """Manually trigger a backup (runs in background thread)."""
    from app.services.backup_service import backup_to_cos

    def _run():
        try:
            backup_to_cos()
        except Exception as e:
            logger.error(f"Manual backup trigger failed: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"message": "Backup triggered, check logs for result."}
