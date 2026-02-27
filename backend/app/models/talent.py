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

    talents = relationship("Talent", secondary="talent_tags", back_populates="tags")


class EntryLog(Base):
    __tablename__ = "entry_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    source = Column(String(20), default="manual")  # manual / pdf / import
    status = Column(String(20), default="done")  # processing / done / failed
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
