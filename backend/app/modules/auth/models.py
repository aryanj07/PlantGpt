"""SQLAlchemy model for the Auth Module's user directory (plan Section
J.2, G.1 `users` table). Phase 5: replaces the Phase 0 in-memory
placeholder in users.py - resolve_or_provision()'s shape is unchanged, so
auth/service.py needed no changes.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    auth0_sub: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
