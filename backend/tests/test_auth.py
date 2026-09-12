"""Tests for the Auth Module (plan Section J.2): Auth0 token verification,
backend session-JWT issuance/refresh, auto-provisioning, and the
dev-mode-header fallback. A locally generated RSA keypair stands in for
Auth0's own signing key so these tests never touch the network - the same
"inject a fake transport" pattern used for the LLM Gateway tests
(httpx.MockTransport), just applied to Auth0's JWKS endpoint instead of a
chat-completions endpoint.
"""

import time

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt as jose_jwt

from app.config import get_settings
from app.main import app
from app.modules.auth.auth0 import Auth0TokenError, Auth0Verifier
from app.modules.auth.service import exchange_auth0_token, refresh_token
from app.modules.auth.tokens import mint_token
from app.modules.auth.users import directory as user_directory

TEST_DOMAIN = "test-tenant.us.auth0.com"
TEST_AUDIENCE = "https://plantgpt.api"
TEST_KID = "test-kid"

client = TestClient(app)


def _b64url_uint(value: int) -> str:
    import base64

    byte_length = (value.bit_length() + 7) // 8 or 1
    return base64.urlsafe_b64encode(value.to_bytes(byte_length, "big")).rstrip(b"=").decode("ascii")


def _generate_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": TEST_KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }
    return private_key, {"keys": [jwk]}


_PRIVATE_KEY, _JWKS = _generate_keypair()


def _sign_auth0_token(*, sub: str, audience: str = TEST_AUDIENCE, domain: str = TEST_DOMAIN, expires_in: int = 3600) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "iss": f"https://{domain}/",
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
    }
    return jose_jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256", headers={"kid": TEST_KID})


def _mock_verifier(*, domain: str = TEST_DOMAIN, audience: str = TEST_AUDIENCE) -> Auth0Verifier:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_JWKS)

    return Auth0Verifier(domain=domain, audience=audience, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture(autouse=True)
def _clear_user_directory():
    user_directory._by_auth0_sub.clear()
    yield
    user_directory._by_auth0_sub.clear()


@pytest.mark.anyio
async def test_valid_auth0_token_mints_backend_session() -> None:
    token = _sign_auth0_token(sub="auth0|operator-1")
    session = await exchange_auth0_token(auth0_access_token=token, verifier=_mock_verifier())

    assert session.tenant_id == "default"
    assert session.roles == ["admin"]
    assert session.token_type == "bearer"
    assert session.expires_in > 0


@pytest.mark.anyio
async def test_same_auth0_subject_maps_to_same_identity_across_calls() -> None:
    token = _sign_auth0_token(sub="auth0|operator-2")
    first = await exchange_auth0_token(auth0_access_token=token, verifier=_mock_verifier())
    second = await exchange_auth0_token(auth0_access_token=token, verifier=_mock_verifier())

    assert first.user_id == second.user_id
    assert first.tenant_id == second.tenant_id


@pytest.mark.anyio
async def test_token_signed_by_untrusted_key_is_rejected() -> None:
    other_private_key, _ = _generate_keypair()
    now = int(time.time())
    bad_token = jose_jwt.encode(
        {"sub": "auth0|imposter", "iss": f"https://{TEST_DOMAIN}/", "aud": TEST_AUDIENCE, "iat": now, "exp": now + 3600},
        other_private_key,
        algorithm="RS256",
        headers={"kid": TEST_KID},  # same kid, different key -> signature mismatch
    )

    with pytest.raises(Exception):  # HTTPException(401) raised by exchange_auth0_token
        await exchange_auth0_token(auth0_access_token=bad_token, verifier=_mock_verifier())


@pytest.mark.anyio
async def test_expired_auth0_token_is_rejected() -> None:
    expired_token = _sign_auth0_token(sub="auth0|expired", expires_in=-10)

    with pytest.raises(Exception):
        await exchange_auth0_token(auth0_access_token=expired_token, verifier=_mock_verifier())


@pytest.mark.anyio
async def test_wrong_audience_is_rejected() -> None:
    token = _sign_auth0_token(sub="auth0|wrong-aud", audience="https://someone-else.api")

    with pytest.raises(Exception):
        await exchange_auth0_token(auth0_access_token=token, verifier=_mock_verifier())


def test_unconfigured_auth0_verifier_raises_clear_error() -> None:
    verifier = Auth0Verifier(domain="", audience="")
    import anyio

    with pytest.raises(Auth0TokenError):
        anyio.run(verifier.verify, "irrelevant")


def test_refresh_reissues_token_with_same_identity() -> None:
    settings = get_settings()
    original, _ = mint_token(settings=settings, user_id="u1", tenant_id="t1", roles=["operator"])

    refreshed = refresh_token(current_token=original)

    assert refreshed.user_id == "u1"
    assert refreshed.tenant_id == "t1"
    assert refreshed.roles == ["operator"]
    assert refreshed.access_token != original  # a genuinely new token (new jti/iat), not the same string


def test_backend_jwt_grants_access_to_protected_chat_endpoint() -> None:
    settings = get_settings()
    token, _ = mint_token(settings=settings, user_id="real-user", tenant_id="real-tenant", roles=["operator"])

    response = client.post("/v1/conversations", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["tenant_id"] == "real-tenant"
    assert response.json()["user_id"] == "real-user"


def test_tampered_backend_jwt_is_rejected() -> None:
    settings = get_settings()
    token, _ = mint_token(settings=settings, user_id="u1", tenant_id="t1", roles=["operator"])
    # Flip a character in the middle rather than the last one: base64url's
    # final character can sit on a padding-bit boundary where a different
    # character still decodes to the same bytes, occasionally making an
    # end-of-token tamper a silent no-op.
    mid = len(token) // 2
    flipped_char = "A" if token[mid] != "A" else "B"
    tampered = token[:mid] + flipped_char + token[mid + 1 :]

    response = client.post("/v1/conversations", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 401


def test_dev_headers_still_work_when_no_authorization_header_present() -> None:
    response = client.post(
        "/v1/conversations", headers={"X-Dev-Tenant-Id": "dev-t", "X-Dev-User-Id": "dev-u"}
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "dev-t"


def test_session_endpoint_rejects_invalid_auth0_token() -> None:
    response = client.post("/v1/auth/session", json={"auth0_access_token": "not-a-real-token"})
    assert response.status_code == 401


def test_refresh_endpoint_requires_bearer_header() -> None:
    response = client.post("/v1/auth/refresh")
    assert response.status_code == 401
