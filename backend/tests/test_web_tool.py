"""Tests for the Tavily web search/extract client (Phase 4 plan, sub-task 3)."""

import json

import httpx
import pytest

from app.modules.llm_gateway.reliability import ProviderError
from app.modules.mcp.tools.web_tool import WebToolClient


def _client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_search_sends_query_and_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.tavily.com/search")
        assert request.headers["authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["query"] == "cement kiln emissions regulations"
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "EPA Cement Rules", "url": "https://epa.gov/x", "content": "..."},
                ]
            },
        )

    client = WebToolClient(api_key="test-key", client=_client_with(handler))
    results = await client.search("cement kiln emissions regulations")

    assert results == [{"title": "EPA Cement Rules", "url": "https://epa.gov/x", "content": "..."}]


@pytest.mark.anyio
async def test_extract_sends_url_and_parses_raw_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://api.tavily.com/extract")
        body = json.loads(request.content)
        assert body["urls"] == ["https://example.com/page"]
        return httpx.Response(
            200,
            json={"results": [{"url": "https://example.com/page", "raw_content": "page text"}]},
        )

    client = WebToolClient(api_key="test-key", client=_client_with(handler))
    result = await client.extract("https://example.com/page")

    assert result == {"url": "https://example.com/page", "content": "page text"}


@pytest.mark.anyio
async def test_extract_returns_none_when_no_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [], "failed_results": ["https://bad.example"]})

    client = WebToolClient(api_key="test-key", client=_client_with(handler))
    assert await client.extract("https://bad.example") is None


@pytest.mark.anyio
async def test_rate_limit_raises_transient_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow down"})

    client = WebToolClient(api_key="test-key", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        await client.search("hi")
    assert exc_info.value.is_transient is True


@pytest.mark.anyio
async def test_auth_failure_raises_non_transient_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    client = WebToolClient(api_key="bad-key", client=_client_with(handler))

    with pytest.raises(ProviderError) as exc_info:
        await client.search("hi")
    assert exc_info.value.is_transient is False
