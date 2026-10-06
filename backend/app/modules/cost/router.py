"""Cost/Quota Module HTTP surface. Answers plan Section K.3's "which tenant
is burning the most AI spend" for the caller's own tenant - there's no
cross-tenant view yet since there's no admin/RBAC concept to gate it behind."""

from fastapi import APIRouter, Depends

from app.modules.auth.schemas import CurrentIdentity
from app.modules.auth.service import get_current_identity
from app.modules.cost.schemas import UsageOut
from app.modules.cost.tracker import get_cost_tracker

router = APIRouter()


@router.get("/usage", response_model=UsageOut)
def get_usage(identity: CurrentIdentity = Depends(get_current_identity)) -> UsageOut:
    snapshot = get_cost_tracker().snapshot(tenant_id=identity.tenant_id)
    return UsageOut(
        tenant_id=snapshot.tenant_id,
        tokens_used=snapshot.tokens_used,
        cost_usd=snapshot.cost_usd,
        budget_usd=snapshot.budget_usd,
        remaining_usd=snapshot.remaining_usd,
    )
