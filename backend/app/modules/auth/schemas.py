from pydantic import BaseModel


class CurrentIdentity(BaseModel):
    tenant_id: str
    user_id: str
    roles: list[str] = ["operator"]


class SessionExchangeRequest(BaseModel):
    auth0_access_token: str


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: str
    user_id: str
    roles: list[str]
