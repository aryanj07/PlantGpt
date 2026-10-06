"""User directory for the Auth Module (plan Section J.2, G.1 `users`
table). Phase 5: real Postgres via SQLAlchemy, replacing the Phase 0
in-memory placeholder - resolve_or_provision()'s shape is unchanged, so
auth/service.py needed no changes.

Real multi-tenant assignment (or reading tenant/role from an Auth0 custom
claim, the plan's stated alternative) still replaces DEFAULT_TENANT_ID/
DEFAULT_ROLES later - correct for a solo builder with exactly one tenant
right now, unaffected by moving off the in-memory dict.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.db import SessionLocal
from app.modules.auth.models import User

DEFAULT_TENANT_ID = "default"
DEFAULT_ROLES = ["admin"]


@dataclass
class ProvisionedUser:
    user_id: str
    tenant_id: str
    roles: list[str]


class UserDirectory:
    def resolve_or_provision(self, auth0_sub: str) -> ProvisionedUser:
        db = SessionLocal()
        try:
            existing = db.scalar(select(User).where(User.auth0_sub == auth0_sub))
            if existing is not None:
                return ProvisionedUser(
                    user_id=existing.id, tenant_id=existing.tenant_id, roles=list(existing.roles)
                )

            user = User(auth0_sub=auth0_sub, tenant_id=DEFAULT_TENANT_ID, roles=list(DEFAULT_ROLES))
            db.add(user)
            db.commit()
            db.refresh(user)
            return ProvisionedUser(user_id=user.id, tenant_id=user.tenant_id, roles=list(user.roles))
        finally:
            db.close()

    def clear_all(self) -> None:
        """Test-only: wipes every provisioned user. Real code never calls this."""
        db = SessionLocal()
        try:
            db.query(User).delete()
            db.commit()
        finally:
            db.close()


directory = UserDirectory()
