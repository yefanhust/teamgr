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
    from app.models.talent import Talent, Tag, TalentTag, EntryLog, LoginAttempt, CardDimension, LLMUsageLog  # noqa
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_default_dimensions()


def _migrate_schema():
    """Add missing columns to existing tables (lightweight migration)."""
    inspector = inspect(engine)
    migrations = [
        ("entry_logs", "status", "TEXT DEFAULT 'done'"),
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
                schema='{"age": "", "gender": "", "location": "", "hometown": ""}',
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
