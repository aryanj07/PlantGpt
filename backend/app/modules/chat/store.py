"""Chat/Conversation Module persistence (plan Section D, E). Phase 5: real
Postgres via SQLAlchemy, replacing the Phase 0 in-memory placeholder - same
public method shapes as before, so chat/service.py needed no changes. A
plain sync SQLAlchemy Session per call, same pattern already established by
rag/service.py and rag/ingestion.py (this backend's Postgres access is sync
throughout, not the separate async SQLAlchemy engine/session flavor).
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.db import SessionLocal
from app.modules.chat.models import Conversation, Message


class SqlChatStore:
    def create_conversation(self, *, tenant_id: str, user_id: str, title: str | None = None) -> Conversation:
        db = SessionLocal()
        try:
            conv = Conversation(tenant_id=tenant_id, user_id=user_id, title=title)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            return conv
        finally:
            db.close()

    def get_conversation(self, *, conversation_id: str, tenant_id: str) -> Conversation | None:
        db = SessionLocal()
        try:
            conv = db.get(Conversation, conversation_id)
            if conv is None or conv.tenant_id != tenant_id:
                # Tenant check mirrors the ownership check the Chat Module
                # must do server-side (plan Section E step 6) - never trust
                # a bare ID lookup without it.
                return None
            return conv
        finally:
            db.close()

    def list_conversations(self, *, tenant_id: str, user_id: str) -> list[Conversation]:
        db = SessionLocal()
        try:
            stmt = select(Conversation).where(
                Conversation.tenant_id == tenant_id, Conversation.user_id == user_id
            )
            return list(db.scalars(stmt).all())
        finally:
            db.close()

    def add_message(
        self,
        *,
        conversation_id: str,
        tenant_id: str,
        role: str,
        content: str,
        citations: list[dict] | None = None,
    ) -> Message:
        db = SessionLocal()
        try:
            msg = Message(
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                role=role,
                content=content,
                citations=citations,
            )
            db.add(msg)
            conv = db.get(Conversation, conversation_id)
            if conv is not None:
                conv.updated_at = datetime.now(UTC)
            db.commit()
            db.refresh(msg)
            return msg
        finally:
            db.close()

    def list_messages(self, *, conversation_id: str, tenant_id: str) -> list[Message]:
        if self.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id) is None:
            return []
        db = SessionLocal()
        try:
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id, Message.tenant_id == tenant_id)
                .order_by(Message.created_at)
            )
            return list(db.scalars(stmt).all())
        finally:
            db.close()


store = SqlChatStore()
