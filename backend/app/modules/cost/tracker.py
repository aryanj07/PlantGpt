"""Cost/Quota Module (plan Section D, G.1, H.1). Real-time per-tenant
token/cost metering plus a hard budget stop, checked before the LLM Gateway
call (plan Section E step 7) so a request never even reaches a provider once
a tenant is over budget - and recorded after the call using the usage the
Gateway captured from whichever adapter actually served the reply
(LLMGateway.get_last_call_info() for streaming, GatewayReply fields for the
non-streaming path).

Pricing (PRICING_USD_PER_1M_TOKENS below) is a hand-maintained
approximation, not fetched live from any provider - update it to match real
billing before trusting this for anything beyond dev-safety. Any model not
listed falls back to DEFAULT_PRICING_USD_PER_1M_TOKENS, deliberately priced
high enough to fail loud (hit the budget sooner) rather than silently
undercount an unknown model's real cost.
"""

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.modules.cost.store import ledger

# $ per 1,000,000 tokens, as (prompt_rate, completion_rate).
PRICING_USD_PER_1M_TOKENS: dict[str, tuple[float, float]] = {
    "openrouter/free": (0.0, 0.0),
    "gpt-5": (5.00, 15.00),
    "gpt-5-mini": (0.25, 2.00),
}
DEFAULT_PRICING_USD_PER_1M_TOKENS = (10.00, 30.00)


class BudgetExceededError(Exception):
    def __init__(self, *, tenant_id: str, spent_usd: float, budget_usd: float) -> None:
        super().__init__(
            f"tenant '{tenant_id}' has spent ${spent_usd:.4f} of its ${budget_usd:.2f} budget"
        )
        self.tenant_id = tenant_id
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd


@dataclass
class UsageSnapshot:
    tenant_id: str
    tokens_used: int
    cost_usd: float
    budget_usd: float

    @property
    def remaining_usd(self) -> float:
        return max(self.budget_usd - self.cost_usd, 0.0)


class CostTracker:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _budget_for(self, tenant_id: str) -> float:
        # V1: one flat budget for every tenant - there's no plan/tier data
        # yet to key a real per-tenant budget off (plan Section Q).
        del tenant_id
        return self._settings.default_monthly_budget_usd

    def check_budget(self, *, tenant_id: str) -> None:
        usage = ledger.get_or_create(tenant_id)
        budget = self._budget_for(tenant_id)
        if usage.cost_usd >= budget:
            raise BudgetExceededError(tenant_id=tenant_id, spent_usd=usage.cost_usd, budget_usd=budget)

    def record(self, *, tenant_id: str, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        prompt_rate, completion_rate = PRICING_USD_PER_1M_TOKENS.get(
            model, DEFAULT_PRICING_USD_PER_1M_TOKENS
        )
        cost_usd = (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000

        usage = ledger.get_or_create(tenant_id)
        usage.tokens_used += prompt_tokens + completion_tokens
        usage.cost_usd += cost_usd

    def snapshot(self, *, tenant_id: str) -> UsageSnapshot:
        usage = ledger.get_or_create(tenant_id)
        return UsageSnapshot(
            tenant_id=tenant_id,
            tokens_used=usage.tokens_used,
            cost_usd=usage.cost_usd,
            budget_usd=self._budget_for(tenant_id),
        )


def get_cost_tracker() -> CostTracker:
    return CostTracker()
