"""SQLAlchemy engine/session scaffold.

No models are defined here yet — the real tenants/users/conversations/messages
schema + Row-Level Security policies are a Phase 1 task owned by Rimsha (plan
Section O). This module only wires the plumbing so that work has somewhere to
land. `chat`'s in-memory store (Phase 0) does not use this yet.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
