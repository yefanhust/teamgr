from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship, backref
from app.database import Base


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(100), default="")
    joined_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="members")
    talent = relationship("Talent")


class ProjectUpdate(Base):
    __tablename__ = "project_updates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    talent_id = Column(Integer, ForeignKey("talents.id", ondelete="SET NULL"), nullable=True)
    raw_input = Column(Text, nullable=False)
    parsed_data = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="updates")
    talent = relationship("Talent")


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    name_pinyin = Column(String(500), default="")
    name_pinyin_initials = Column(String(100), default="")
    description = Column(Text, default="")
    status = Column(String(20), default="active")  # active / completed / archived
    parent_id = Column(Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    last_update_at = Column(DateTime, nullable=True)
    llm_summary = Column(Text, default="")
    llm_summary_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    children = relationship("Project", backref=backref("parent", remote_side="Project.id"))
    updates = relationship("ProjectUpdate", back_populates="project", cascade="all, delete-orphan")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
