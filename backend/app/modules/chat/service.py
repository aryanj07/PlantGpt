"""Chat/Conversation Module (plan Section D, E). Phase 0: wired against the
in-memory store below; Phase 1 replaces the store with real Postgres
persistence + ownership checks against RLS-backed tables, without changing
this module's external shape.
"""

from fastapi import HTTPException

from app.modules.chat.store import Conversation, Message, store
from app.modules.llm_gateway.gateway import HISTORY_LIMIT, LLMGateway, get_llm_gateway


def create_conversation(*, tenant_id: str, user_id: str) -> Conversation:
    return store.create_conversation(tenant_id=tenant_id, user_id=user_id)


def list_conversations(*, tenant_id: str, user_id: str) -> list[Conversation]:
    return store.list_conversations(tenant_id=tenant_id, user_id=user_id)


def list_messages(*, tenant_id: str, conversation_id: str) -> list[Message]:
    conv = store.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return store.list_messages(conversation_id=conversation_id, tenant_id=tenant_id)


async def post_user_message(
    *,
    tenant_id: str,
    conversation_id: str,
    content: str,
    llm_gateway: LLMGateway | None = None,
) -> tuple[Message, Message]:
    """Mirrors plan Section E: persist the user message first, then call the
    LLM Gateway for the assistant reply. Rate limiting (step 5) and cost/quota
    checks (step 7) are not wired in yet - those modules are still stubs
    (Phase 1/2) and must sit here, before the gateway call, once implemented.
    """
    conv = store.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="user", content=content
    )

    prior_history = [
        {"role": m.role, "content": m.content}
        for m in store.list_messages(conversation_id=conversation_id, tenant_id=tenant_id)
        if m.id != user_message.id
    ][-HISTORY_LIMIT:]

    gateway = llm_gateway or get_llm_gateway()
    reply = await gateway.generate(system_prompt="", history=prior_history, user_message=content)

    assistant_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="assistant", content=reply.content
    )

    return user_message, assistant_message
