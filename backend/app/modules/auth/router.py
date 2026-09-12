"""Auth Module HTTP surface (plan Section J.2)."""

from fastapi import APIRouter, Header, HTTPException

from app.modules.auth import service
from app.modules.auth.schemas import SessionExchangeRequest, SessionResponse

router = APIRouter()


@router.post("/session", response_model=SessionResponse)
async def create_session(body: SessionExchangeRequest) -> SessionResponse:
    """Exchange a client-obtained Auth0 access token for a PlantGPT session
    token. The Auth0 login itself (Authorization Code + PKCE) happens
    client-side; this endpoint never sees a password."""
    return await service.exchange_auth0_token(auth0_access_token=body.auth0_access_token)


@router.post("/refresh", response_model=SessionResponse)
def refresh(authorization: str | None = Header(default=None)) -> SessionResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <session token>.")
    return service.refresh_token(current_token=authorization[7:])
