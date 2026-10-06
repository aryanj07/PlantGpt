"""SQLAlchemy model for the Cost/Quota Module's usage ledger (plan Section
G.1 `quota_ledger`). Phase 5: replaces the Phase 0 in-memory placeholder in
store.py, and adds period_start - the in-memory version never reset a
tenant's usage, so hitting budget once meant being locked out for the life
of the process; in production (long-lived, rarely restarted) that's
effectively permanent, not just "until next restart".
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class TenantUsage(Base):
    __tablename__ = "tenant_usage"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
