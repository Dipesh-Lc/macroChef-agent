from collections.abc import Generator

from app.config import Settings, get_settings
from app.data.db import SessionLocal


def get_app_settings() -> Settings:
    return get_settings()


def get_db_session() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
