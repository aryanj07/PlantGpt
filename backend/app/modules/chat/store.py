"""Phase 0 placeholder persistence: a process-local in-memory store. Real
Postgres persistence (tenants/users/conversations/messages schema + RLS) is a
Phase 1 task owned by Rimsha (plan Section G.1, O). Nothing here survives a
process restart and there is no cross-instance consistency - do not build on
top of this beyond the Phase 0 skeleton.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class Conversation:
    id: str
    tenant_id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Message:
    id: str
    conversation_id: str
    tenant_id: str
    role: str
    content: str
    created_at: datetime
    is_pending: bool = False


class InMemoryChatStore:
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}

    def create_conversation(self, *, tenant_id: str, user_id: str, title: str | None = None) -> Conversation:
        now = datetime.now(UTC)
        conv = Conversation(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._conversations[conv.id] = conv
        self._messages[conv.id] = []
        return conv

    def get_conversation(self, *, conversation_id: str, tenant_id: str) -> Conversation | None:
        conv = self._conversations.get(conversation_id)
        if conv is None or conv.tenant_id != tenant_id:
            # Tenant check mirrors the ownership check the real Chat Module
            # must do server-side (plan Section E step 6) - even in this
            # in-memory stand-in, never skip it.
            return None
        return conv

    def list_conversations(self, *, tenant_id: str, user_id: str) -> list[Conversation]:
        return [
            c
            for c in self._conversations.values()
            if c.tenant_id == tenant_id and c.user_id == user_id
        ]

    def add_message(self, *, conversation_id: str, tenant_id: str, role: str, content: str) -> Message:
        msg = Message(
            id=str(uuid.uuid4()),
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC),
        )
        self._messages.setdefault(conversation_id, []).append(msg)
        self._conversations[conversation_id].updated_at = msg.created_at
        return msg

    def list_messages(self, *, conversation_id: str, tenant_id: str) -> list[Message]:
        if self.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id) is None:
            return []
        return list(self._messages.get(conversation_id, []))


store = InMemoryChatStore()
