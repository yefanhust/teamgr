from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Date, JSON
from app.database import Base


class DailyMenu(Base):
    __tablename__ = "daily_menus"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, unique=True, nullable=False)
    adult_count = Column(Integer, default=1)
    menu_data = Column(JSON)
    raw_response = Column(Text)
    model_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
