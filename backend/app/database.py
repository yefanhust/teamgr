import logging
import os
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger(__name__)

# Database path - use environment variable or default
DB_DIR = os.environ.get("TEAMGR_DATA_DIR", os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data"
))
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "teamgr.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models.talent import (  # noqa
        Talent, Tag, TalentTag, EntryLog, LoginAttempt,
        CardDimension, LLMUsageLog, PresetQuestion, ScheduledQueryResult,
        IdeaFragment, IdeaInputLog, IdeaInsight,
    )
    from app.models.todo import TodoItem, TodoTag, TodoItemTag, TodoAnalysis  # noqa
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_default_dimensions()
    _migrate_personal_info_birthday()
    _seed_default_preset_questions()


def _migrate_schema():
    """Add missing columns to existing tables (lightweight migration)."""
    inspector = inspect(engine)
    migrations = [
        ("entry_logs", "status", "TEXT DEFAULT 'done'"),
        ("tags", "parent_id", "INTEGER REFERENCES tags(id) ON DELETE SET NULL"),
        ("todo_items", "deadline", "DATE"),
        ("todo_items", "description", "TEXT DEFAULT ''"),
        ("todo_items", "repeat_rule", "TEXT"),
        ("todo_items", "repeat_interval", "INTEGER DEFAULT 1"),
        ("todo_items", "repeat_next_at", "DATE"),
        ("todo_items", "repeat_source_id", "INTEGER REFERENCES todo_items(id) ON DELETE SET NULL"),
        ("todo_items", "repeat_include_weekends", "BOOLEAN DEFAULT 0"),
        ("todo_items", "vibe_status", "TEXT"),
        ("todo_items", "vibe_summary", "TEXT"),
        ("todo_items", "vibe_plan", "TEXT"),
        ("todo_items", "vibe_commit_id", "TEXT"),
        ("todo_items", "vibe_session_id", "TEXT"),
        ("todo_analyses", "model_name", "TEXT"),
        ("idea_insights", "model_name", "TEXT DEFAULT ''"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            if table not in inspector.get_table_names():
                continue
            existing_cols = [c["name"] for c in inspector.get_columns(table)]
            if column not in existing_cols:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                conn.commit()
                logger.info(f"Migration: added {table}.{column}")


def _seed_default_dimensions():
    from app.models.talent import CardDimension
    db = SessionLocal()
    try:
        existing = db.query(CardDimension).count()
        if existing > 0:
            return

        defaults = [
            CardDimension(
                key="personal_info",
                label="个人信息",
                schema='{"birthday": "", "age": "", "gender": "", "location": "", "hometown": ""}',
                is_default=True,
                sort_order=0,
            ),
            CardDimension(
                key="basic_info",
                label="基本背景",
                schema='{"education": "", "university": "", "major": "", "certifications": []}',
                is_default=True,
                sort_order=1,
            ),
            CardDimension(
                key="professional",
                label="专业能力",
                schema='{"years_of_experience": "", "expertise_areas": [], "tech_stack": [], "current_focus": ""}',
                is_default=True,
                sort_order=2,
            ),
            CardDimension(
                key="strengths",
                label="优势",
                schema='[]',
                is_default=True,
                sort_order=3,
            ),
            CardDimension(
                key="weaknesses",
                label="劣势",
                schema='[]',
                is_default=True,
                sort_order=4,
            ),
            CardDimension(
                key="personality",
                label="性格特征",
                schema='{"work_style": "", "communication": "", "leadership": ""}',
                is_default=True,
                sort_order=5,
            ),
            CardDimension(
                key="potential",
                label="发展潜力",
                schema='{"growth_direction": "", "suitable_roles": [], "development_suggestions": []}',
                is_default=True,
                sort_order=6,
            ),
            CardDimension(
                key="notes",
                label="备注",
                schema='""',
                is_default=True,
                sort_order=7,
            ),
            CardDimension(
                key="one_liner",
                label="一句话总结",
                schema='""',
                is_default=True,
                sort_order=8,
            ),
        ]
        db.add_all(defaults)
        db.commit()
    finally:
        db.close()


def _migrate_personal_info_birthday():
    """Ensure personal_info dimension schema includes birthday field."""
    import json as _json
    from app.models.talent import CardDimension, Talent
    db = SessionLocal()
    try:
        dim = db.query(CardDimension).filter(CardDimension.key == "personal_info").first()
        if dim:
            schema = _json.loads(dim.schema) if dim.schema else {}
            if "birthday" not in schema:
                schema = {"birthday": "", **schema}
                dim.schema = _json.dumps(schema, ensure_ascii=False)
                db.commit()
                logger.info("Migration: added birthday to personal_info schema")
        # Also add birthday field to existing talents' card_data (use raw SQL for reliable JSON update)
        from sqlalchemy import text
        talents = db.query(Talent).all()
        for t in talents:
            cd = t.card_data or {}
            pi = cd.get("personal_info")
            if isinstance(pi, dict) and "birthday" not in pi:
                pi["birthday"] = ""
                new_cd = {**cd, "personal_info": pi}
                db.execute(
                    text("UPDATE talents SET card_data = :data WHERE id = :id"),
                    {"data": _json.dumps(new_cd, ensure_ascii=False), "id": t.id},
                )
        db.commit()
    finally:
        db.close()


def _seed_default_preset_questions():
    from app.models.talent import PresetQuestion
    db = SessionLocal()
    try:
        existing = db.query(PresetQuestion).count()
        if existing > 0:
            return

        defaults = [
            PresetQuestion(question="未来15天有哪些人过生日？", sort_order=0),
            PresetQuestion(question="有哪些33、34岁的人才？", sort_order=1),
            PresetQuestion(question="有哪些35岁及以上的人才？", sort_order=2),
        ]
        db.add_all(defaults)
        db.commit()
    finally:
        db.close()
