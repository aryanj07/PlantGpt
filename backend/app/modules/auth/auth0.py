"""Auth0 token verification (plan Section J.2).

Fetches Auth0's JWKS (JSON Web Key Set) and verifies inbound Auth0 access
tokens against it - standard OIDC/OAuth2 resource-server verification. No
Auth0 SDK needed for this half: it's just RS256 JWT verification against a
remote public key set, which python-jose already does. The Auth0 SDK (or
plain OAuth2 Authorization Code + PKCE) lives client-side instead, where the
actual login UI happens - that's a separate client task, not this module.
"""

import time
from dataclasses import dataclass

import httpx
from jose import jwt
from jose.exceptions import JOSEError


@dataclass
class Auth0Claims:
    sub: str
    raw: dict


class Auth0TokenError(Exception):
    pass


class Auth0Verifier:
    def __init__(
        self,
        *,
        domain: str,
        audience: str,
        client: httpx.AsyncClient | None = None,
        cache_ttl_seconds: float = 3600,
    ) -> None:
        self._domain = domain.rstrip("/")
        self._audience = audience
        self._client = client or httpx.AsyncClient()
        self._cache_ttl_seconds = cache_ttl_seconds
        self._jwks: dict | None = None
        self._jwks_fetched_at: float = 0.0

    async def _get_jwks(self) -> dict:
        now = time.monotonic()
        if self._jwks is None or (now - self._jwks_fetched_at) > self._cache_ttl_seconds:
            response = await self._client.get(f"https://{self._domain}/.well-known/jwks.json")
            response.raise_for_status()
            self._jwks = response.json()
            self._jwks_fetched_at = now
        return self._jwks

    async def verify(self, token: str) -> Auth0Claims:
        if not self._domain or not self._audience:
            raise Auth0TokenError("Auth0 is not configured (AUTH0_DOMAIN/AUTH0_AUDIENCE unset).")

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JOSEError as exc:
            raise Auth0TokenError("malformed token") from exc

        jwks = await self._get_jwks()
        key = next(
            (k for k in jwks.get("keys", []) if k.get("kid") == unverified_header.get("kid")), None
        )
        if key is None:
            raise Auth0TokenError("signing key not found in JWKS")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=f"https://{self._domain}/",
            )
        except JOSEError as exc:
            raise Auth0TokenError(str(exc)) from exc

        sub = claims.get("sub")
        if not sub:
            raise Auth0TokenError("token missing 'sub' claim")
        return Auth0Claims(sub=sub, raw=claims)
