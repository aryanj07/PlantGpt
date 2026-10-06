"""Auth Module (plan Section D, J.2).

Flow: the client authenticates with Auth0 directly (Authorization Code +
PKCE, client-side - that's a separate client task, not this module), then
presents the resulting Auth0 access token to POST /v1/auth/session. This
module verifies that token against Auth0's JWKS (auth0.py), resolves or
auto-provisions a PlantGPT identity for it (users.py), and mints the
backend's own short-lived JWT (tokens.py). Every other endpoint only ever
sees that backend JWT, never the Auth0 token itself.

DEV-MODE fallback: while settings.dev_mode is true and no Authorization
header is present, X-Dev-Tenant-Id/X-Dev-User-Id headers are still accepted
so the Phase 0 skeleton and its tests keep working without a live Auth0
round-trip on every request. This must be deleted, not just disabled, once
dev_mode is retired for good.
"""

from fastapi import Header, HTTPException

from app.config import Settings, get_settings
from app.modules.auth.auth0 import Auth0TokenError, Auth0Verifier
from app.modules.auth.schemas import CurrentIdentity, SessionResponse
from app.modules.auth.tokens import BackendTokenError, mint_token, verify_token
from app.modules.auth.users import directory


def get_auth0_verifier(settings: Settings | None = None) -> Auth0Verifier:
    settings = settings or get_settings()
    return Auth0Verifier(domain=settings.auth0_domain, audience=settings.auth0_audience)


async def exchange_auth0_token(
    *,
    auth0_access_token: str,
    settings: Settings | None = None,
    verifier: Auth0Verifier | None = None,
) -> SessionResponse:
    settings = settings or get_settings()
    verifier = verifier or get_auth0_verifier(settings)

    try:
        claims = await verifier.verify(auth0_access_token)
    except Auth0TokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Auth0 token: {exc}") from exc

    provisioned = directory.resolve_or_provision(claims.sub)
    token, ttl_seconds = mint_token(
        settings=settings,
        user_id=provisioned.user_id,
        tenant_id=provisioned.tenant_id,
        roles=provisioned.roles,
    )
    return SessionResponse(
        access_token=token,
        expires_in=ttl_seconds,
        tenant_id=provisioned.tenant_id,
        user_id=provisioned.user_id,
        roles=provisioned.roles,
    )


def refresh_token(*, current_token: str, settings: Settings | None = None) -> SessionResponse:
    settings = settings or get_settings()
    try:
        claims = verify_token(settings=settings, token=current_token)
    except BackendTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session token.") from exc

    token, ttl_seconds = mint_token(
        settings=settings, user_id=claims["sub"], tenant_id=claims["tenant_id"], roles=claims["roles"]
    )
    return SessionResponse(
        access_token=token,
        expires_in=ttl_seconds,
        tenant_id=claims["tenant_id"],
        user_id=claims["sub"],
        roles=claims["roles"],
    )


def get_current_identity(
    authorization: str | None = Header(default=None),
    x_dev_tenant_id: str | None = Header(default=None),
    x_dev_user_id: str | None = Header(default=None),
) -> CurrentIdentity:
    settings = get_settings()

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
        try:
            claims = verify_token(settings=settings, token=token)
        except BackendTokenError as exc:
            raise HTTPException(status_code=401, detail="Invalid or expired session token.") from exc
        return CurrentIdentity(
            tenant_id=claims["tenant_id"], user_id=claims["sub"], roles=claims.get("roles", [])
        )

    if settings.dev_mode and x_dev_tenant_id and x_dev_user_id:
        return CurrentIdentity(tenant_id=x_dev_tenant_id, user_id=x_dev_user_id)

    detail = "Missing credentials: send Authorization: Bearer <session token>"
    if settings.dev_mode:
        detail += " or X-Dev-Tenant-Id/X-Dev-User-Id in dev mode."
    raise HTTPException(status_code=401, detail=detail)
