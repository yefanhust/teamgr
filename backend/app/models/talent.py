from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Table
)
from sqlalchemy.orm import relationship
from app.database import Base


class TalentTag(Base):
    __tablename__ = "talent_tags"
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)


class Talent(Base):
    __tablename__ = "talents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    name_pinyin = Column(String(500), default="")
    name_pinyin_initials = Column(String(100), default="")
    email = Column(String(200), default="")
    phone = Column(String(50), default="")
    current_role = Column(String(200), default="")
    department = Column(String(200), default="")
    card_data = Column(JSON, default=dict)
    summary = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tags = relationship("Tag", secondary="talent_tags", back_populates="talents")
    entry_logs = relationship("EntryLog", back_populates="talent", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    color = Column(String(20), default="#3B82F6")
    parent_id = Column(Integer, ForeignKey("tags.id", ondelete="SET NULL"), nullable=True)

    parent = relationship("Tag", remote_side="Tag.id", backref="children")
    talents = relationship("Talent", secondary="talent_tags", back_populates="tags")


class EntryLog(Base):
    __tablename__ = "entry_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(20), default="manual")  # manual / pdf / image / import
    status = Column(String(20), default="done")  # processing / done / failed
    model_name = Column(String(100), default="")  # LLM model used for parsing (pdf/image)
    llm_response = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    talent = relationship("Talent", back_populates="entry_logs")


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(45), nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    success = Column(Boolean, default=False)


class CardDimension(Base):
    __tablename__ = "card_dimensions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(100), unique=True, nullable=False)
    label = Column(String(100), nullable=False)
    schema = Column(Text, default="{}")  # JSON string defining the structure
    is_default = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    model_name = Column(String(100), nullable=False)
    call_type = Column(String(30), nullable=False)  # text-entry / pdf-parse / semantic-search
    duration_ms = Column(Integer, nullable=False)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)


class PresetQuestion(Base):
    __tablename__ = "preset_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    is_scheduled = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    scheduled_results = relationship(
        "ScheduledQueryResult",
        back_populates="preset_question",
        cascade="all, delete-orphan",
    )


class ScheduledQueryResult(Base):
    __tablename__ = "scheduled_query_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    preset_question_id = Column(
        Integer,
        ForeignKey("preset_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question_snapshot = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    model_name = Column(String(100), nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)

    preset_question = relationship("PresetQuestion", back_populates="scheduled_results")


class IdeaFragment(Base):
    """A classified and tagged inspiration fragment."""
    __tablename__ = "idea_fragments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(100), default="")
    tags = Column(JSON, default=list)  # ["tag1", "tag2"]
    source_input_ids = Column(JSON, default=list)  # [input_log_id, ...]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IdeaInputLog(Base):
    """Raw input history for the inspiration space."""
    __tablename__ = "idea_input_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_text = Column(Text, nullable=False)
    status = Column(String(20), default="processing")  # processing / done / failed
    llm_response = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class IdeaInsight(Base):
    """Daily LLM-generated insights from all idea fragments."""
    __tablename__ = "idea_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    reasoning = Column(Text, default="")
    liked = Column(Boolean, default=False)
    generated_date = Column(String(10), nullable=False)  # "2026-03-06"
    model_name = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
