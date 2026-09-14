"""Cost/Quota ledger persistence (plan Section G.1 `quota_ledger`). Phase 5:
real Postgres via SQLAlchemy, replacing the Phase 0 in-memory placeholder.

Unlike the in-memory version, get_or_create() can no longer hand back a
live mutable reference the caller free-mutates (there's nothing to mutate
in place once "state" means database rows, not a shared Python dict) - so
record() now does an explicit, atomic read-modify-write instead of
CostTracker mutating whatever get_or_create() returned. It also resets a
tenant's usage when period_start has rolled into a new calendar month - the
in-memory ledger never reset at all, which is fine for a dev process
restarted often but not for a production one restarted rarely: a tenant
that ever hit budget would otherwise stay locked out permanently.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from app.db import SessionLocal
from app.modules.cost.models import TenantUsage as TenantUsageRow


@dataclass
class TenantUsage:
    tenant_id: str
    tokens_used: int = 0
    cost_usd: float = 0.0


def _same_period(period_start: datetime, now: datetime) -> bool:
    return (period_start.year, period_start.month) == (now.year, now.month)


class SqlCostLedger:
    def get_or_create(self, tenant_id: str) -> TenantUsage:
        db = SessionLocal()
        try:
            now = datetime.now(UTC)
            row = db.get(TenantUsageRow, tenant_id)
            if row is None:
                row = TenantUsageRow(tenant_id=tenant_id, period_start=now)
                db.add(row)
                db.commit()
                db.refresh(row)
            elif not _same_period(row.period_start, now):
                row.tokens_used = 0
                row.cost_usd = 0.0
                row.period_start = now
                db.commit()
                db.refresh(row)
            return TenantUsage(tenant_id=row.tenant_id, tokens_used=row.tokens_used, cost_usd=row.cost_usd)
        finally:
            db.close()

    def record(self, *, tenant_id: str, tokens: int, cost_usd: float) -> None:
        # get_or_create's own session already closed by the time we'd see
        # its row, and it may have just reset the period - re-run the
        # same fresh-or-reset logic here rather than trust a stale read.
        db = SessionLocal()
        try:
            now = datetime.now(UTC)
            row = db.get(TenantUsageRow, tenant_id)
            if row is None:
                row = TenantUsageRow(tenant_id=tenant_id, period_start=now, tokens_used=0, cost_usd=0.0)
                db.add(row)
            elif not _same_period(row.period_start, now):
                row.tokens_used = 0
                row.cost_usd = 0.0
                row.period_start = now
            row.tokens_used += tokens
            row.cost_usd += cost_usd
            db.commit()
        finally:
            db.close()

    def set_usage(self, *, tenant_id: str, tokens_used: int, cost_usd: float) -> None:
        """Test/ops-only: directly overwrites a tenant's usage row
        (creating it if needed). The request path always goes through
        record(), never this."""
        db = SessionLocal()
        try:
            row = db.get(TenantUsageRow, tenant_id)
            if row is None:
                row = TenantUsageRow(tenant_id=tenant_id, period_start=datetime.now(UTC))
                db.add(row)
            row.tokens_used = tokens_used
            row.cost_usd = cost_usd
            db.commit()
        finally:
            db.close()

    def clear_all(self) -> None:
        """Test-only: wipes every tenant's usage row. Real code never calls this."""
        db = SessionLocal()
        try:
            db.query(TenantUsageRow).delete()
            db.commit()
        finally:
            db.close()


ledger = SqlCostLedger()
