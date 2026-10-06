"""Tests for MCPToolBroker.run() (Phase 4 plan, sub-task 4). Web tool calls
use a fake WebToolClient rather than a real httpx mock - the request/response
shape is already covered by test_web_tool.py; this only checks the broker's
routing and context/citation assembly.
"""

import pytest

from app.modules.mcp.broker import MCPToolBroker


class _FakeWebToolClient:
    def __init__(self, *, search_results=None, extract_result=None) -> None:
        self._search_results = search_results or []
        self._extract_result = extract_result
        self.search_calls: list[str] = []
        self.extract_calls: list[str] = []

    async def search(self, query: str, *, max_results: int = 5) -> list[dict]:
        self.search_calls.append(query)
        return self._search_results

    async def extract(self, url: str) -> dict | None:
        self.extract_calls.append(url)
        return self._extract_result


@pytest.mark.anyio
async def test_sensor_query_returns_simulated_context_and_citation() -> None:
    broker = MCPToolBroker()
    result = await broker.run(query="What is the current temperature of kiln 2?")

    assert result is not None
    assert "simulated" in result.context_text.lower()
    assert result.citations == [
        {"document_id": "sensor:temperature", "title": "Simulated sensor reading", "source_uri": None}
    ]


@pytest.mark.anyio
async def test_unmatched_sensor_query_is_honest_about_no_data() -> None:
    broker = MCPToolBroker()
    result = await broker.run(query="What's the status of work order 4521?")

    assert result is not None
    assert "no live data source" in result.context_text.lower()


@pytest.mark.anyio
async def test_web_search_query_returns_results_and_citations() -> None:
    fake = _FakeWebToolClient(
        search_results=[{"title": "EPA Cement Rules", "url": "https://epa.gov/x", "content": "..."}]
    )
    broker = MCPToolBroker(web_client=fake)

    result = await broker.run(query="Search the web for the latest cement emissions regulations.")

    assert fake.search_calls == ["Search the web for the latest cement emissions regulations."]
    assert result is not None
    assert "external web search" in result.context_text.lower()
    assert result.citations == [
        {"document_id": "https://epa.gov/x", "title": "EPA Cement Rules", "source_uri": "https://epa.gov/x"}
    ]


@pytest.mark.anyio
async def test_web_extract_query_scrapes_the_url_in_the_query() -> None:
    fake = _FakeWebToolClient(
        extract_result={"url": "https://example.com/report", "content": "report text"}
    )
    broker = MCPToolBroker(web_client=fake)

    result = await broker.run(query="Summarize https://example.com/report for me.")

    assert fake.extract_calls == ["https://example.com/report"]
    assert result is not None
    assert "report text" in result.context_text


@pytest.mark.anyio
async def test_web_search_without_configured_client_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patched rather than relying on TAVILY_API_KEY being absent from the
    # environment - this backend's real .env has a real key configured.
    monkeypatch.setattr("app.modules.mcp.broker.get_web_tool_client", lambda: None)
    broker = MCPToolBroker(web_client=None)

    with pytest.raises(RuntimeError):
        await broker.run(query="Search the web for something.")
