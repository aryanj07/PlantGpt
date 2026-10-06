"""Backend-issued session JWT (plan Section J.2): short-lived, HS256, signed
with a secret only this backend holds - never the Auth0 token itself. This
is what decouples PlantGPT's tenant/role model from whatever Auth0 (or a
future different identity provider) issues; every endpoint other than
POST /v1/auth/session only ever sees this token.
"""

import time
import uuid

from jose import jwt
from jose.exceptions import JOSEError

from app.config import Settings

ALGORITHM = "HS256"


class BackendTokenError(Exception):
    pass


def mint_token(*, settings: Settings, user_id: str, tenant_id: str, roles: list[str]) -> tuple[str, int]:
    now = int(time.time())
    ttl_seconds = settings.jwt_ttl_minutes * 60
    claims = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "roles": roles,
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)
    return token, ttl_seconds


def verify_token(*, settings: Settings, token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], issuer=settings.jwt_issuer)
    except JOSEError as exc:
        raise BackendTokenError(str(exc)) from exc
