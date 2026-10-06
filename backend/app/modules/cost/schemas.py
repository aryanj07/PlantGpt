from pydantic import BaseModel


class UsageOut(BaseModel):
    tenant_id: str
    tokens_used: int
    cost_usd: float
    budget_usd: float
    remaining_usd: float
