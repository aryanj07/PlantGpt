"""Placeholder user directory (plan Section J.2, G.1 `users` table).

Maps an Auth0 subject to a PlantGPT tenant_id/user_id/roles, auto-
provisioning a single default tenant on first sight - correct for a solo
builder with exactly one tenant right now. Real multi-tenant assignment (or
reading tenant/role from an Auth0 custom claim, the plan's stated
alternative) replaces this once the Postgres `users` table (Phase 1 schema
task, still blocked on Postgres being stood up) exists.

Process-local and non-persistent - same caveat as chat/store.py. Restarting
the backend forgets every provisioned identity.
"""

import uuid
from dataclasses import dataclass

DEFAULT_TENANT_ID = "default"
DEFAULT_ROLES = ["admin"]


@dataclass
class ProvisionedUser:
    user_id: str
    tenant_id: str
    roles: list[str]


class UserDirectory:
    def __init__(self) -> None:
        self._by_auth0_sub: dict[str, ProvisionedUser] = {}

    def resolve_or_provision(self, auth0_sub: str) -> ProvisionedUser:
        existing = self._by_auth0_sub.get(auth0_sub)
        if existing is not None:
            return existing
        provisioned = ProvisionedUser(
            user_id=str(uuid.uuid4()), tenant_id=DEFAULT_TENANT_ID, roles=list(DEFAULT_ROLES)
        )
        self._by_auth0_sub[auth0_sub] = provisioned
        return provisioned


directory = UserDirectory()
