"""Tests for the OpenAI embeddings client (Phase 3 plan, sub-task 3)."""

import json

import httpx
import pytest

from app.modules.llm_gateway.reliability import ProviderError
from app.modules.rag.embeddings import EmbeddingsClient


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_embed_sends_model_and_input_and_returns_vectors_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "text-embedding-3-small"
        assert body["input"] == ["first", "second"]
        # Deliberately out of order in the response - the client must sort by index.
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.2, 0.2]},
                    {"index": 0, "embedding": [0.1, 0.1]},
                ]
            },
        )

    client = EmbeddingsClient(api_key="test-key", client=_client_with(handler))
    vectors = await client.embed(["first", "second"])

    assert vectors == [[0.1, 0.1], [0.2, 0.2]]


@pytest.mark.anyio
async def test_embed_empty_input_makes_no_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("embed([]) must not make a network request")

    client = EmbeddingsClient(api_key="test-key", client=_client_with(handler))
    assert await client.embed([]) == []


@pytest.mark.anyio
async def test_rate_limit_raises_transient_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    client = EmbeddingsClient(api_key="test-key", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        await client.embed(["hi"])
    assert exc_info.value.is_transient is True


@pytest.mark.anyio
async def test_auth_failure_raises_non_transient_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    client = EmbeddingsClient(api_key="bad-key", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        await client.embed(["hi"])
    assert exc_info.value.is_transient is False
