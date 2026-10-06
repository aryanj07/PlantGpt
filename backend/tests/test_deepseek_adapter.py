"""Tests for the DeepSeek adapter (plan Section O Phase 2: third LLM Gateway
provider). Same MockTransport pattern as test_llm_gateway.py/test_streaming.py
- DeepSeek's API is claimed OpenAI-compatible, so these largely mirror the
OpenRouter adapter's own tests.
"""

import json

import httpx
import pytest

from app.modules.llm_gateway.adapters.deepseek_adapter import DeepSeekAdapter
from app.modules.llm_gateway.gateway import LLMGateway, _Route
from app.modules.llm_gateway.reliability import ProviderError


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _sse_body(chunks: list[str], *, usage: dict | None = None) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}\n\n" for c in chunks]
    if usage:
        lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


@pytest.mark.anyio
async def test_non_streaming_send_returns_content_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "deepseek-flash"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Kiln burning zone is ~1450C."}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        )

    adapter = DeepSeekAdapter(api_key="test-key", model="deepseek-flash", client=_client_with(handler))
    chunks = [
        c
        async for c in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="deepseek-flash", stream=False
        )
    ]

    assert chunks == ["Kiln burning zone is ~1450C."]
    assert adapter.last_usage == {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}


@pytest.mark.anyio
async def test_streaming_send_yields_deltas_and_captures_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(
            200, content=_sse_body(["Kiln ", "temp."], usage={"prompt_tokens": 5, "completion_tokens": 3})
        )

    adapter = DeepSeekAdapter(api_key="k", model="deepseek-flash", client=_client_with(handler))
    chunks = [
        c
        async for c in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="deepseek-flash", stream=True
        )
    ]

    assert chunks == ["Kiln ", "temp."]
    assert adapter.last_usage == {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 0}


@pytest.mark.anyio
async def test_auth_failure_is_not_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    adapter = DeepSeekAdapter(api_key="bad", model="deepseek-flash", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        async for _ in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="deepseek-flash", stream=False
        ):
            pass
    assert exc_info.value.is_transient is False


@pytest.mark.anyio
async def test_rate_limit_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    adapter = DeepSeekAdapter(api_key="k", model="deepseek-flash", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        async for _ in adapter.send(
            system_prompt="sys", history=[], user_message="hi", model="deepseek-flash", stream=False
        ):
            pass
    assert exc_info.value.is_transient is True


@pytest.mark.anyio
async def test_wired_into_gateway_as_a_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "from deepseek"}}]})

    adapter = DeepSeekAdapter(api_key="k", model="deepseek-flash", client=_client_with(handler))
    gateway = LLMGateway([_Route(name="deepseek", adapter=adapter, model="deepseek-flash")])

    reply = await gateway.generate(system_prompt="", history=[], user_message="hi")

    assert reply.content == "from deepseek"
    assert reply.model_used == "deepseek:deepseek-flash"
