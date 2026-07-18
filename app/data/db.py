from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

# Neon (and some other Postgres hosts) can hand out a `postgres://` URL, but
# SQLAlchemy 2.x dropped the `postgres://` alias for the `postgresql://`
# dialect -- create_engine() raises NoSuchModuleError on it. Normalize
# defensively here rather than relying on the upstream secret always being
# spelled `postgresql://`.
database_url = settings.database_url
if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]

connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    from app.data import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
