from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class TodoItemTag(Base):
    __tablename__ = "todo_item_tags"
    todo_id = Column(Integer, ForeignKey("todo_items.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("todo_tags.id", ondelete="CASCADE"), primary_key=True)


class TodoTag(Base):
    __tablename__ = "todo_tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    color = Column(String(20), default="#3B82F6")
    parent_id = Column(Integer, ForeignKey("todo_tags.id", ondelete="SET NULL"), nullable=True)
    scope = Column(String(20), default="todo")  # "todo" or "requirement"

    parent = relationship("TodoTag", remote_side="TodoTag.id", backref="children")
    todos = relationship("TodoItem", secondary="todo_item_tags", back_populates="tags")


class TodoItem(Base):
    __tablename__ = "todo_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, default="")
    high_priority = Column(Boolean, default=False)
    deadline = Column(Date, nullable=True)
    deadline_time = Column(String(11), nullable=True)  # "HH:MM" or "HH:MM-HH:MM" or null
    # Repeat config: rule is "daily"/"weekly"/"monthly"/"yearly", interval is N units
    repeat_rule = Column(String(20), nullable=True)   # null = not repeating
    repeat_interval = Column(Integer, default=1)       # every N days/weeks/months/years
    repeat_next_at = Column(Date, nullable=True)       # next date to spawn a new todo
    repeat_include_weekends = Column(Boolean, default=False)  # False = skip weekends
    repeat_source_id = Column(Integer, ForeignKey("todo_items.id", ondelete="SET NULL"), nullable=True)
    vibe_status = Column(String(20), nullable=True)  # null, "planning", "implementing", "verifying", "committed"
    vibe_plan = Column(Text, nullable=True)  # implementation plan from LLM
    vibe_summary = Column(Text, nullable=True)  # summary of changes when moving to verifying
    vibe_commit_id = Column(String(40), nullable=True)  # git commit hash
    vibe_session_id = Column(String(100), nullable=True)  # Claude Code session ID
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tags = relationship("TodoTag", secondary="todo_item_tags", back_populates="todos")


class TodoAnalysis(Base):
    """Daily LLM-generated efficiency analysis of completed todos."""
    __tablename__ = "todo_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    generated_date = Column(String(10), nullable=False)  # "2026-03-06"
    model_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
