"""Placeholder cost/quota ledger (plan Section G.1 `quota_ledger` table).

Process-local, non-persistent, no period boundaries yet - same caveat as
chat/store.py and auth/users.py: this is a running total since the process
started, not a real billing-period ledger. Real Postgres persistence with
period_start/period_end is a later task, blocked on Postgres being stood up
(same blocker noted throughout Phase 1).
"""

from dataclasses import dataclass


@dataclass
class TenantUsage:
    tenant_id: str
    tokens_used: int = 0
    cost_usd: float = 0.0


class CostLedger:
    def __init__(self) -> None:
        self._usage: dict[str, TenantUsage] = {}

    def get_or_create(self, tenant_id: str) -> TenantUsage:
        usage = self._usage.get(tenant_id)
        if usage is None:
            usage = TenantUsage(tenant_id=tenant_id)
            self._usage[tenant_id] = usage
        return usage


ledger = CostLedger()
