"""Cost/Quota Module scaffold (plan Section D, G.1 quota_ledger). Phase 2,
owner: Rimsha (infra) + Prince (per-provider token accounting)."""


class CostTracker:
    def record(self, *, tenant_id: str, prompt_tokens: int, completion_tokens: int, model: str) -> None:
        raise NotImplementedError("Real per-tenant cost metering lands in Phase 2 (plan Section H.1).")

    def budget_remaining(self, *, tenant_id: str) -> float:
        raise NotImplementedError("Real budget tracking lands in Phase 2.")
