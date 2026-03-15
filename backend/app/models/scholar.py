from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey
from app.database import Base


class ScholarScheduledQuestion(Base):
    __tablename__ = "scholar_scheduled_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    schedule_type = Column(String(20), nullable=False)  # daily / weekly / monthly
    cron_hour = Column(Integer, default=6)
    cron_minute = Column(Integer, default=0)
    day_of_week = Column(String(10), default="mon")  # for weekly
    day_of_month = Column(Integer, default=1)  # for monthly
    depends_on_id = Column(Integer, ForeignKey("scholar_scheduled_questions.id", ondelete="SET NULL"), nullable=True)
    context_days = Column(Integer, default=7)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScholarScheduledResult(Base):
    __tablename__ = "scholar_scheduled_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question_id = Column(Integer, ForeignKey("scholar_scheduled_questions.id", ondelete="CASCADE"), nullable=False)
    question_snapshot = Column(Text, default="")
    answer = Column(Text, default="")
    period_label = Column(String(30), default="")
    schedule_type = Column(String(20), default="")
    status = Column(String(20), default="success")  # success / failed
    model_name = Column(String(50), default="claude-code-cli")
    generated_at = Column(DateTime, default=datetime.utcnow)
    duration_seconds = Column(Float, default=0.0)
