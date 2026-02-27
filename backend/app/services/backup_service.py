import os
import logging
import shutil
from datetime import datetime
from app.config import get_cos_config, get_backup_config
from app.database import DB_PATH

logger = logging.getLogger(__name__)


def backup_to_cos():
    """Backup SQLite database to Tencent Cloud COS."""
    cos_cfg = get_cos_config()
    backup_cfg = get_backup_config()

    if not backup_cfg.get("enabled", False):
        logger.info("Backup is disabled in config")
        return

    if not cos_cfg.get("enabled", False):
        logger.info("COS is disabled in config")
        return

    secret_id = cos_cfg.get("secret_id", "")
    secret_key = cos_cfg.get("secret_key", "")
    region = cos_cfg.get("region", "ap-guangzhou")
    bucket = cos_cfg.get("bucket", "")
    prefix = cos_cfg.get("backup_prefix", "teamgr-backup/")

    if not all([secret_id, secret_key, bucket]):
        logger.warning("COS credentials not fully configured, skipping backup")
        return

    if not os.path.exists(DB_PATH):
        logger.warning(f"Database file not found at {DB_PATH}, skipping backup")
        return

    # Create a copy to avoid locking issues
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"teamgr_{timestamp}.db"
    temp_path = f"/tmp/{backup_filename}"

    try:
        shutil.copy2(DB_PATH, temp_path)

        from qcloud_cos import CosConfig, CosS3Client

        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
        )
        client = CosS3Client(config)

        cos_key = f"{prefix}{backup_filename}"
        client.upload_file(
            Bucket=bucket,
            LocalFilePath=temp_path,
            Key=cos_key,
        )

        logger.info(f"Database backup uploaded to COS: {cos_key}")

        # Also upload as 'latest.db' for easy restore
        latest_key = f"{prefix}latest.db"
        client.upload_file(
            Bucket=bucket,
            LocalFilePath=temp_path,
            Key=latest_key,
        )

    except ImportError:
        logger.error("cos-python-sdk-v5 not installed, cannot backup to COS")
    except Exception as e:
        logger.error(f"COS backup failed: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def setup_backup_scheduler():
    """Set up APScheduler for daily backup."""
    backup_cfg = get_backup_config()
    if not backup_cfg.get("enabled", False):
        logger.info("Backup scheduler disabled")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            backup_to_cos,
            "cron",
            hour=backup_cfg.get("cron_hour", 3),
            minute=backup_cfg.get("cron_minute", 0),
            id="daily_backup",
        )
        scheduler.start()
        logger.info(
            f"Backup scheduler started: daily at "
            f"{backup_cfg.get('cron_hour', 3):02d}:{backup_cfg.get('cron_minute', 0):02d}"
        )
        return scheduler
    except Exception as e:
        logger.error(f"Failed to start backup scheduler: {e}")
        return None
