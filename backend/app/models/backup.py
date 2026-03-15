from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from app.database import Base


class BackupLog(Base):
    __tablename__ = "backup_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), nullable=False)  # success / failed
    file_size = Column(Integer, default=0)  # backup package size in bytes
    cos_key = Column(String(200), default="")  # COS object key
    error_message = Column(Text, default="")  # failure reason
    encrypted = Column(Boolean, default=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
