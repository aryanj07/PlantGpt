"""Chat/Conversation Module (plan Section D, E). Phase 0: wired against the
in-memory store below; Phase 1 replaces the store with real Postgres
persistence + ownership checks against RLS-backed tables, without changing
this module's external shape.
"""

import json
from collections.abc import AsyncIterator

from fastapi import HTTPException

from app.modules.chat.schemas import MessageOut
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


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _message_payload(message: Message) -> dict:
    return MessageOut(**message.__dict__).model_dump(mode="json")


async def stream_assistant_reply(
    *,
    tenant_id: str,
    conversation_id: str,
    content: str,
    llm_gateway: LLMGateway | None = None,
) -> AsyncIterator[str]:
    """SSE body for POST .../messages/stream (plan ADR 5). Persists the user
    message up front exactly like post_user_message, then streams the
    assistant reply chunk by chunk - the full text is only persisted once
    the stream actually completes, so a mid-stream failure can never leave a
    half-written message in the store.

    Auth/ownership failures happen in the router before this generator ever
    starts (a normal HTTP error, since no bytes have been sent yet). Once
    this generator is running, the HTTP response is already committed to
    200 + text/event-stream, so every failure from here on is reported as
    an SSE "error" event instead of an HTTP status - the same distinction
    plan Section I draws between provider outages and data loss: the user's
    message is never lost, even if the assistant's reply is degraded.
    """
    conv = store.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id)
    if conv is None:
        yield _sse({"type": "error", "detail": "Conversation not found."})
        return

    user_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="user", content=content
    )
    yield _sse({"type": "user_message", "message": _message_payload(user_message)})

    prior_history = [
        {"role": m.role, "content": m.content}
        for m in store.list_messages(conversation_id=conversation_id, tenant_id=tenant_id)
        if m.id != user_message.id
    ][-HISTORY_LIMIT:]

    gateway = llm_gateway or get_llm_gateway()
    buffer: list[str] = []
    try:
        async for delta in gateway.generate_stream(
            system_prompt="", history=prior_history, user_message=content
        ):
            buffer.append(delta)
            yield _sse({"type": "delta", "content": delta})
    except Exception as exc:  # noqa: BLE001 - reported as an SSE event, not raised past a started stream
        yield _sse({"type": "error", "detail": str(exc)})

    full_text = "".join(buffer) or "AI temporarily unavailable, your message was saved."
    assistant_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="assistant", content=full_text
    )
    yield _sse({"type": "done", "message": _message_payload(assistant_message)})
