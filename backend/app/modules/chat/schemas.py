from datetime import datetime

from pydantic import BaseModel


class ConversationOut(BaseModel):
    id: str
    tenant_id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    is_pending: bool = False


class CreateMessageRequest(BaseModel):
    content: str
