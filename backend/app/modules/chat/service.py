"""Chat/Conversation Module (plan Section D, E). Phase 0: wired against the
in-memory store below; Phase 1 replaces the store with real Postgres
persistence + ownership checks against RLS-backed tables, without changing
this module's external shape.
"""

import json
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException

from app.modules.chat.schemas import MessageOut
from app.modules.chat.store import Conversation, Message, store
from app.modules.cost.tracker import BudgetExceededError, CostTracker, get_cost_tracker
from app.modules.llm_gateway.gateway import HISTORY_LIMIT, LLMGateway, get_llm_gateway
from app.modules.router.classifier import classify

logger = logging.getLogger("plantgpt")


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
    cost_tracker: CostTracker | None = None,
) -> tuple[Message, Message]:
    """Mirrors plan Section E: persist the user message first (step 6), then
    the Cost/Quota Module's budget check (step 7) - before any LLM call, so
    an over-budget tenant never even reaches a provider - then the LLM
    Gateway for the assistant reply. Rate limiting (step 5) is still not
    wired in (a separate Phase 1 task, not yet done).
    """
    conv = store.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="user", content=content
    )

    # RequestRouter v1 (plan Section H.3). TODO(Phase 3/4): once
    # RAGService.retrieve() and MCPToolBroker.dispatch() are real (not
    # NotImplementedError stubs), branch on `route` here instead of only
    # logging it - NEEDS_RAG/NEEDS_TOOL/NEEDS_RAG_AND_TOOL should compose
    # retrieval and/or bounded tool calls before the Gateway call below.
    route = classify(content)
    logger.info("route_classified route=%s conversation_id=%s", route.value, conversation_id)

    tracker = cost_tracker or get_cost_tracker()
    try:
        tracker.check_budget(tenant_id=tenant_id)
    except BudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    prior_history = [
        {"role": m.role, "content": m.content}
        for m in store.list_messages(conversation_id=conversation_id, tenant_id=tenant_id)
        if m.id != user_message.id
    ][-HISTORY_LIMIT:]

    gateway = llm_gateway or get_llm_gateway()
    reply = await gateway.generate(system_prompt="", history=prior_history, user_message=content)

    if reply.prompt_tokens is not None and reply.completion_tokens is not None:
        tracker.record(
            tenant_id=tenant_id,
            model=reply.model,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
        )

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
    cost_tracker: CostTracker | None = None,
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

    # See the matching TODO in post_user_message - same log-only wiring.
    route = classify(content)
    logger.info("route_classified route=%s conversation_id=%s", route.value, conversation_id)

    tracker = cost_tracker or get_cost_tracker()
    try:
        tracker.check_budget(tenant_id=tenant_id)
    except BudgetExceededError as exc:
        yield _sse({"type": "error", "detail": str(exc)})
        yield _sse(
            {
                "type": "done",
                "message": _message_payload(
                    store.add_message(
                        conversation_id=conversation_id,
                        tenant_id=tenant_id,
                        role="assistant",
                        content=f"Message not sent: {exc}",
                    )
                ),
            }
        )
        return

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

    call_info = gateway.get_last_call_info()
    if call_info is not None:
        model, usage = call_info
        if usage is not None:
            tracker.record(
                tenant_id=tenant_id,
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
            )

    full_text = "".join(buffer) or "AI temporarily unavailable, your message was saved."
    assistant_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="assistant", content=full_text
    )
    yield _sse({"type": "done", "message": _message_payload(assistant_message)})
