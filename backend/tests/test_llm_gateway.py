"""Tests for the LLM Gateway (plan Section H.1, I): routing, retry/backoff,
circuit breaker, and fallback - mirroring the test patterns already used for
the Flutter OpenRouterChatRepository/FreeRouterChatRepository
(test/open_router_chat_repository_test.dart,
test/free_router_chat_repository_test.dart), which inject a mock HTTP client
rather than hitting the network. httpx.MockTransport is the server-side
equivalent of http/testing.dart's MockClient.
"""

import httpx
import pytest

from app.modules.llm_gateway.adapters.openrouter_adapter import OpenRouterAdapter
from app.modules.llm_gateway.gateway import LLMGateway, _Route
from app.modules.llm_gateway.reliability import CircuitBreaker


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _openrouter_route(client: httpx.AsyncClient, *, max_retries: int = 2) -> _Route:
    adapter = OpenRouterAdapter(api_key="test-key", model="openrouter/free", client=client)
    return _Route(name="openrouter", adapter=adapter, model="openrouter/free", max_retries=max_retries)


@pytest.mark.anyio
async def test_no_routes_returns_unconfigured_stub() -> None:
    gateway = LLMGateway([])
    reply = await gateway.generate(system_prompt="", history=[], user_message="What is a clinker cooler?")
    assert reply.model_used == "unconfigured"
    assert "clinker cooler" in reply.content


@pytest.mark.anyio
async def test_successful_call_returns_provider_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "Normal burning-zone temp is ~1450C."}}]})

    route = _openrouter_route(_client_with(handler))
    gateway = LLMGateway([route])

    reply = await gateway.generate(system_prompt="", history=[], user_message="Kiln temp?")

    assert reply.content == "Normal burning-zone temp is ~1450C."
    assert reply.model_used == "openrouter:openrouter/free"


@pytest.mark.anyio
async def test_transient_error_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "provider down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "recovered"}}]})

    route = _openrouter_route(_client_with(handler))
    gateway = LLMGateway([route])

    reply = await gateway.generate(system_prompt="", history=[], user_message="hi")

    assert reply.content == "recovered"
    assert calls["n"] == 3  # 2 failures + 1 success, matching max_retries=2


@pytest.mark.anyio
async def test_non_transient_error_does_not_retry() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, json={"error": "bad key"})

    route = _openrouter_route(_client_with(handler))
    gateway = LLMGateway([route])

    reply = await gateway.generate(system_prompt="", history=[], user_message="hi")

    assert calls["n"] == 1  # no retry on a non-transient (auth) failure
    assert "temporarily unavailable" in reply.content


@pytest.mark.anyio
async def test_exhausted_route_falls_back_to_next_route() -> None:
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "down"})

    def working_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "fallback worked"}}]})

    primary = _openrouter_route(_client_with(failing_handler), max_retries=0)
    primary.name = "openrouter-primary"
    fallback = _openrouter_route(_client_with(working_handler), max_retries=0)
    fallback.name = "openrouter-fallback"

    gateway = LLMGateway([primary, fallback])
    reply = await gateway.generate(system_prompt="", history=[], user_message="hi")

    assert reply.content == "fallback worked"
    assert reply.model_used.startswith("openrouter-fallback")


@pytest.mark.anyio
async def test_circuit_breaker_opens_after_repeated_failures_and_skips_calls() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, json={"error": "down"})

    route = _openrouter_route(_client_with(handler), max_retries=0)
    route.breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=999)
    gateway = LLMGateway([route])

    await gateway.generate(system_prompt="", history=[], user_message="1")
    await gateway.generate(system_prompt="", history=[], user_message="2")
    calls_before_open = calls["n"]

    # Breaker should now be open; a third call must not reach the transport.
    reply = await gateway.generate(system_prompt="", history=[], user_message="3")

    assert calls["n"] == calls_before_open
    assert reply.model_used == "unconfigured" or "temporarily unavailable" in reply.content
