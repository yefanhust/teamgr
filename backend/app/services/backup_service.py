import io
import os
import logging
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import get_cos_config, get_backup_config
from app.database import DB_PATH, DB_DIR, SessionLocal

logger = logging.getLogger(__name__)

# Project root: two levels up from backend/app/
_PROJECT_ROOT = Path(os.environ.get(
    "TEAMGR_DATA_DIR", DB_DIR
)).resolve().parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_DATA_DIR = Path(DB_DIR).resolve()


# ---------------------------------------------------------------------------
# AES-256-GCM encryption helpers
# ---------------------------------------------------------------------------

def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from password using PBKDF2."""
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_file(src_path: str, dst_path: str, password: str):
    """Encrypt a file with AES-256-GCM.

    Output format: [16B salt][12B nonce][ciphertext+tag]
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(16)
    key = _derive_key(password, salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)

    with open(src_path, "rb") as f:
        plaintext = f.read()

    ciphertext = aesgcm.encrypt(nonce, plaintext, None)

    with open(dst_path, "wb") as f:
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)


def decrypt_file(src_path: str, dst_path: str, password: str):
    """Decrypt an AES-256-GCM encrypted file."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    with open(src_path, "rb") as f:
        salt = f.read(16)
        nonce = f.read(12)
        ciphertext = f.read()

    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)

    with open(dst_path, "wb") as f:
        f.write(plaintext)


# ---------------------------------------------------------------------------
# SQLite safe backup
# ---------------------------------------------------------------------------

def _sqlite_backup(src_db_path: str, dst_db_path: str):
    """Use SQLite backup API to safely copy database (handles WAL)."""
    src = sqlite3.connect(src_db_path)
    dst = sqlite3.connect(dst_db_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


# ---------------------------------------------------------------------------
# Tar.gz packing
# ---------------------------------------------------------------------------

def _collect_backup_files(tmp_dir: str) -> str:
    """Collect all files to backup into a tar.gz archive. Returns archive path."""
    archive_path = os.path.join(tmp_dir, "backup.tar.gz")

    with tarfile.open(archive_path, "w:gz") as tar:
        # 1. Database (via SQLite backup API)
        db_backup_path = os.path.join(tmp_dir, "teamgr.db")
        if os.path.exists(DB_PATH):
            _sqlite_backup(DB_PATH, db_backup_path)
            tar.add(db_backup_path, arcname="data/teamgr.db")

        # 2. Config files
        config_yaml = _CONFIG_DIR / "config.yaml"
        if config_yaml.exists():
            tar.add(str(config_yaml), arcname="config/config.yaml")

        instructions_yaml = _CONFIG_DIR / "instructions.yaml"
        if instructions_yaml.exists():
            tar.add(str(instructions_yaml), arcname="config/instructions.yaml")

        # 3. Scholar data
        scholar_conv = _DATA_DIR / "scholar-conversations.json"
        if scholar_conv.exists():
            tar.add(str(scholar_conv), arcname="data/scholar-conversations.json")

        scholar_sessions = _DATA_DIR / "scholar-sessions"
        if scholar_sessions.is_dir():
            for f in scholar_sessions.iterdir():
                if f.is_file():
                    tar.add(str(f), arcname=f"data/scholar-sessions/{f.name}")

        scholar_files = _DATA_DIR / "scholar-files"
        if scholar_files.is_dir():
            for root, dirs, files in os.walk(scholar_files):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    arcname = os.path.relpath(fpath, _DATA_DIR)
                    tar.add(fpath, arcname=f"data/{arcname}")

        # 4. Vibe sessions
        vibe_sessions = _DATA_DIR / "vibe-sessions"
        if vibe_sessions.is_dir():
            for f in vibe_sessions.iterdir():
                if f.is_file():
                    tar.add(str(f), arcname=f"data/vibe-sessions/{f.name}")

    return archive_path


# ---------------------------------------------------------------------------
# Backup log helpers
# ---------------------------------------------------------------------------

def _log_backup(status: str, started_at: datetime, cos_key: str = "",
                file_size: int = 0, encrypted: bool = False,
                error_message: str = ""):
    """Write a backup log entry to the database."""
    from app.models.backup import BackupLog
    db = SessionLocal()
    try:
        log = BackupLog(
            status=status,
            file_size=file_size,
            cos_key=cos_key,
            error_message=error_message,
            encrypted=encrypted,
            started_at=started_at,
            completed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write backup log: {e}")
    finally:
        db.close()


def _notify_backup_failure(error_msg: str):
    """Send backup failure notification to ALL enabled bots (critical alert)."""
    try:
        from app.services.notification_service import send_notification_sync
        title = "备份失败告警"
        content = f"**错误信息：**\n{error_msg}\n\n请检查备份配置。"
        send_notification_sync(title, content)
    except Exception as e:
        logger.error(f"Failed to send backup failure notification: {e}")


# ---------------------------------------------------------------------------
# Main backup function
# ---------------------------------------------------------------------------

def backup_to_cos():
    """Backup all critical data to Tencent Cloud COS (encrypted tar.gz)."""
    started_at = datetime.utcnow()

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
    prefix = cos_cfg.get("backup_prefix", "teamgr/")

    if not all([secret_id, secret_key, bucket]):
        error_msg = "COS credentials not fully configured"
        logger.warning(f"{error_msg}, skipping backup")
        _log_backup("failed", started_at, error_message=error_msg)
        _notify_backup_failure(error_msg)
        return

    # Check encryption password
    encryption_password = backup_cfg.get("encryption_password", "")
    if not encryption_password:
        error_msg = "未配置备份加密密码 (backup.encryption_password)，为防止明文泄露，备份已取消"
        logger.warning(error_msg)
        _log_backup("failed", started_at, error_message=error_msg)
        _notify_backup_failure(error_msg)
        return

    if not os.path.exists(DB_PATH):
        error_msg = f"Database file not found at {DB_PATH}"
        logger.warning(error_msg)
        _log_backup("failed", started_at, error_message=error_msg)
        _notify_backup_failure(error_msg)
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp_dir = None

    try:
        tmp_dir = tempfile.mkdtemp(prefix="teamgr_backup_")

        # Step 1: Collect and pack
        archive_path = _collect_backup_files(tmp_dir)

        # Step 2: Encrypt
        encrypted_path = os.path.join(tmp_dir, f"teamgr_{timestamp}.tar.gz.enc")
        encrypt_file(archive_path, encrypted_path, encryption_password)
        file_size = os.path.getsize(encrypted_path)

        # Step 3: Upload to COS
        from qcloud_cos import CosConfig, CosS3Client

        config = CosConfig(
            Region=region,
            SecretId=secret_id,
            SecretKey=secret_key,
        )
        client = CosS3Client(config)

        cos_key = f"{prefix}teamgr_{timestamp}.tar.gz.enc"
        client.upload_file(
            Bucket=bucket,
            LocalFilePath=encrypted_path,
            Key=cos_key,
        )
        logger.info(f"Encrypted backup uploaded to COS: {cos_key} ({file_size} bytes)")

        # Also upload as latest
        latest_key = f"{prefix}latest.tar.gz.enc"
        client.upload_file(
            Bucket=bucket,
            LocalFilePath=encrypted_path,
            Key=latest_key,
        )

        _log_backup("success", started_at, cos_key=cos_key,
                     file_size=file_size, encrypted=True)

    except ImportError:
        error_msg = "cos-python-sdk-v5 or cryptography not installed"
        logger.error(error_msg)
        _log_backup("failed", started_at, error_message=error_msg)
        _notify_backup_failure(error_msg)
    except Exception as e:
        error_msg = str(e)
        logger.error(f"COS backup failed: {error_msg}")
        _log_backup("failed", started_at, error_message=error_msg)
        _notify_backup_failure(error_msg)
    finally:
        # Cleanup temp files
        if tmp_dir and os.path.exists(tmp_dir):
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

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
