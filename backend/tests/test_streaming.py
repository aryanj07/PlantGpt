"""Tests for SSE streaming (plan ADR 5, Phase 2): provider-level adapter
streaming, the Gateway's retry-before-first-chunk semantics, and the actual
POST .../messages/stream endpoint end to end.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.llm_gateway.adapters.openai_adapter import OpenAiAdapter
from app.modules.llm_gateway.adapters.openrouter_adapter import OpenRouterAdapter
from app.modules.llm_gateway.gateway import LLMGateway, _Route
from app.modules.llm_gateway.reliability import ProviderError

client = TestClient(app)
HEADERS = {"X-Dev-Tenant-Id": "tenant-1", "X-Dev-User-Id": "user-1"}


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openrouter_sse_body(chunks: list[str]) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _openai_sse_body(chunks: list[str]) -> bytes:
    lines = [
        f"data: {json.dumps({'type': 'response.output_text.delta', 'delta': c})}\n\n" for c in chunks
    ]
    lines.append(f"data: {json.dumps({'type': 'response.completed'})}\n\n")
    return "".join(lines).encode()


@pytest.mark.anyio
async def test_openrouter_adapter_streams_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=_openrouter_sse_body(["Kiln ", "temp ", "is 1450C."]))

    adapter = OpenRouterAdapter(api_key="k", model="openrouter/free", client=_client_with(handler))
    chunks = [
        c
        async for c in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="openrouter/free", stream=True
        )
    ]

    assert chunks == ["Kiln ", "temp ", "is 1450C."]


@pytest.mark.anyio
async def test_openai_adapter_streams_deltas() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, content=_openai_sse_body(["Normal ", "burning ", "zone."]))

    adapter = OpenAiAdapter(api_key="k", model="gpt-5", client=_client_with(handler))
    chunks = [
        c
        async for c in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="gpt-5", stream=True
        )
    ]

    assert chunks == ["Normal ", "burning ", "zone."]


@pytest.mark.anyio
async def test_openrouter_adapter_stream_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    adapter = OpenRouterAdapter(api_key="k", model="openrouter/free", client=_client_with(handler))

    with pytest.raises(ProviderError):
        async for _ in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="openrouter/free", stream=True
        ):
            pass


@pytest.mark.anyio
async def test_gateway_generate_stream_yields_provider_chunks() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_openrouter_sse_body(["a", "b", "c"]))

    adapter = OpenRouterAdapter(api_key="k", model="openrouter/free", client=_client_with(handler))
    route = _Route(name="openrouter", adapter=adapter, model="openrouter/free", max_retries=2)
    gateway = LLMGateway([route])

    chunks = [c async for c in gateway.generate_stream(system_prompt="", history=[], user_message="hi")]

    assert chunks == ["a", "b", "c"]


@pytest.mark.anyio
async def test_gateway_generate_stream_retries_before_first_chunk() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(503, json={"error": "down"})
        return httpx.Response(200, content=_openrouter_sse_body(["recovered"]))

    adapter = OpenRouterAdapter(api_key="k", model="openrouter/free", client=_client_with(handler))
    route = _Route(name="openrouter", adapter=adapter, model="openrouter/free", max_retries=2)
    gateway = LLMGateway([route])

    chunks = [c async for c in gateway.generate_stream(system_prompt="", history=[], user_message="hi")]

    assert chunks == ["recovered"]
    assert calls["n"] == 2


@pytest.mark.anyio
async def test_gateway_generate_stream_unconfigured() -> None:
    gateway = LLMGateway([])
    chunks = [
        c async for c in gateway.generate_stream(system_prompt="", history=[], user_message="hello there")
    ]
    assert len(chunks) == 1
    assert "hello there" in chunks[0]


def _sse_events(raw_text: str) -> list[dict]:
    events = []
    for block in raw_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data:")
        events.append(json.loads(block[len("data:") :].strip()))
    return events


def test_stream_endpoint_requires_auth() -> None:
    response = client.post(
        "/v1/conversations/does-not-matter/messages/stream", json={"content": "hi"}
    )
    assert response.status_code == 401


def test_stream_endpoint_full_round_trip() -> None:
    conv = client.post("/v1/conversations", headers=HEADERS).json()

    response = client.post(
        f"/v1/conversations/{conv['id']}/messages/stream",
        headers=HEADERS,
        json={"content": "What's the burning-zone temperature?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _sse_events(response.text)
    assert events[0]["type"] == "user_message"
    assert events[0]["message"]["content"] == "What's the burning-zone temperature?"

    delta_events = [e for e in events if e["type"] == "delta"]
    assert delta_events, "expected at least one delta event from the unconfigured-gateway stub"

    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1
    assembled = "".join(e["content"] for e in delta_events)
    assert done_events[0]["message"]["content"] == assembled
    assert done_events[0]["message"]["role"] == "assistant"

    # The full conversation is now persisted exactly as streamed.
    history = client.get(f"/v1/conversations/{conv['id']}/messages", headers=HEADERS).json()
    assert len(history) == 2
    assert history[1]["content"] == assembled


def test_stream_endpoint_conversation_not_found_reports_sse_error() -> None:
    response = client.post(
        "/v1/conversations/does-not-exist/messages/stream",
        headers=HEADERS,
        json={"content": "hi"},
    )

    assert response.status_code == 200
    events = _sse_events(response.text)
    assert events[0]["type"] == "error"
