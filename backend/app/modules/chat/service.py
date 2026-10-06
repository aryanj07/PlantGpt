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
from app.modules.llm_gateway.gateway import HISTORY_LIMIT, SYSTEM_PROMPT, LLMGateway, get_llm_gateway
from app.modules.mcp.broker import MCPToolBroker, get_mcp_tool_broker
from app.modules.rag.service import RAGService, RetrievedChunk, get_rag_service
from app.modules.router.classifier import Route, classify

logger = logging.getLogger("plantgpt")


async def _augment_context(
    *,
    route: Route,
    tenant_id: str,
    content: str,
    rag_service: RAGService | None,
    tool_broker: MCPToolBroker | None,
) -> tuple[str, list[dict] | None]:
    """Returns (system_prompt, citations), combining RAG (Phase 3) and/or an
    MCP tool (Phase 4) depending on route - both fire and their blocks/
    citations are concatenated for NEEDS_RAG_AND_TOOL. Either source failing
    degrades gracefully (logged, skipped) rather than losing the whole reply
    over it - the same "don't turn a degraded path into data loss" instinct
    as the LLM Gateway's own fallback-to-degraded-reply behavior (plan
    Section I)."""
    blocks: list[str] = []
    citations: list[dict] = []

    if route in (Route.NEEDS_RAG, Route.NEEDS_RAG_AND_TOOL):
        try:
            rag = rag_service or get_rag_service()
            chunks = await rag.retrieve(tenant_id=tenant_id, query=content)
        except Exception:  # noqa: BLE001 - retrieval is a nice-to-have, not worth failing the reply over
            logger.exception("RAG retrieval failed, continuing without it")
            chunks = []
        if chunks:
            blocks.append(_build_rag_block(chunks))
            citations.extend(_citations_from_chunks(chunks))

    if route in (Route.NEEDS_TOOL, Route.NEEDS_RAG_AND_TOOL):
        try:
            broker = tool_broker or get_mcp_tool_broker()
            tool_result = await broker.run(query=content)
        except Exception:  # noqa: BLE001 - same degrade-gracefully instinct as RAG above
            logger.exception("MCP tool call failed, continuing without it")
            tool_result = None
        if tool_result is not None:
            blocks.append(tool_result.context_text)
            citations.extend(tool_result.citations)

    if not blocks:
        return "", None
    return f"{SYSTEM_PROMPT}\n\n" + "\n\n".join(blocks), citations or None


def _build_rag_block(chunks: list[RetrievedChunk]) -> str:
    excerpts = "\n\n".join(f"[Source: {c.title}]\n{c.text}" for c in chunks)
    return (
        "Use the following excerpts from the plant's own documentation to "
        "answer the user's question when relevant, and mention the source "
        "title naturally when you rely on one:\n\n" + excerpts
    )


def _citations_from_chunks(chunks: list[RetrievedChunk]) -> list[dict]:
    seen: set[str] = set()
    citations = []
    for c in chunks:
        if c.document_id in seen:
            continue
        seen.add(c.document_id)
        citations.append({"document_id": c.document_id, "title": c.title, "source_uri": c.source_uri})
    return citations


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
    rag_service: RAGService | None = None,
    tool_broker: MCPToolBroker | None = None,
) -> tuple[Message, Message]:
    """Mirrors plan Section E: persist the user message first (step 6), then
    the Cost/Quota Module's budget check (step 7) - before any LLM call, so
    an over-budget tenant never even reaches a provider - then RAG retrieval
    (Phase 3) and the LLM Gateway for the assistant reply. Rate limiting
    (step 5) is still not wired in (a separate Phase 1 task, not yet done).
    """
    conv = store.get_conversation(conversation_id=conversation_id, tenant_id=tenant_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    user_message = store.add_message(
        conversation_id=conversation_id, tenant_id=tenant_id, role="user", content=content
    )

    # RequestRouter v1 (plan Section H.3). Both RAG (Phase 3) and MCP tools
    # (Phase 4) are real now - see _augment_context below.
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

    system_prompt, citations = await _augment_context(
        route=route, tenant_id=tenant_id, content=content, rag_service=rag_service, tool_broker=tool_broker
    )

    gateway = llm_gateway or get_llm_gateway()
    reply = await gateway.generate(system_prompt=system_prompt, history=prior_history, user_message=content)

    if reply.prompt_tokens is not None and reply.completion_tokens is not None:
        tracker.record(
            tenant_id=tenant_id,
            model=reply.model,
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
        )

    assistant_message = store.add_message(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        role="assistant",
        content=reply.content,
        citations=citations,
    )

    return user_message, assistant_message


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _message_payload(message: Message) -> dict:
    # message.__dict__ on a real SQLAlchemy instance (Phase 5) also carries
    # _sa_instance_state - __table__.columns is the same safe pattern
    # chat/router.py's _row_dict and rag/router.py already use.
    row = {c.name: getattr(message, c.name) for c in message.__table__.columns}
    return MessageOut(**row).model_dump(mode="json")


async def stream_assistant_reply(
    *,
    tenant_id: str,
    conversation_id: str,
    content: str,
    llm_gateway: LLMGateway | None = None,
    cost_tracker: CostTracker | None = None,
    rag_service: RAGService | None = None,
    tool_broker: MCPToolBroker | None = None,
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

    # See the matching comment in post_user_message.
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

    system_prompt, citations = await _augment_context(
        route=route, tenant_id=tenant_id, content=content, rag_service=rag_service, tool_broker=tool_broker
    )
    if citations:
        yield _sse({"type": "citations", "citations": citations})

    gateway = llm_gateway or get_llm_gateway()
    buffer: list[str] = []
    try:
        async for delta in gateway.generate_stream(
            system_prompt=system_prompt, history=prior_history, user_message=content
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
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        role="assistant",
        content=full_text,
        citations=citations,
    )
    yield _sse({"type": "done", "message": _message_payload(assistant_message)})
