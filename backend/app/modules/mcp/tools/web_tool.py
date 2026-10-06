"""Web search + scrape tool (Phase 4 plan, sub-task 3): Tavily - a
permanent free tier (1,000 credits/month, no credit card, confirmed via
tavily.com/pricing - not a time-limited trial), covering both search and
extract in one API. Same httpx + ProviderError pattern as
llm_gateway/adapters/ and rag/embeddings.py - reused, not reinvented.
"""

import httpx

from app.config import Settings, get_settings
from app.modules.llm_gateway.reliability import ProviderError

SEARCH_URL = "https://api.tavily.com/search"
EXTRACT_URL = "https://api.tavily.com/extract"


class WebToolClient:
    def __init__(
        self,
        *,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient()
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

    async def _post(self, url: str, body: dict) -> dict:
        try:
            response = await self._client.post(
                url, json=body, headers=self._headers(), timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="tavily", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="tavily", detail=str(exc), is_transient=True) from exc

        if response.status_code == 429:
            raise ProviderError(provider="tavily", detail="rate limited", is_transient=True, status_code=429)
        if response.status_code in (502, 503, 504):
            raise ProviderError(
                provider="tavily", detail="provider failure", is_transient=True, status_code=response.status_code
            )
        if response.status_code != 200:
            raise ProviderError(
                provider="tavily",
                detail=f"request failed with status {response.status_code}: {response.text[:300]}",
                is_transient=False,
                status_code=response.status_code,
            )
        return response.json()

    async def search(self, query: str, *, max_results: int = 5) -> list[dict]:
        data = await self._post(SEARCH_URL, {"query": query, "max_results": max_results})
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
            for r in data.get("results", [])
        ]

    async def extract(self, url: str) -> dict | None:
        data = await self._post(EXTRACT_URL, {"urls": [url]})
        results = data.get("results", [])
        if not results:
            return None
        result = results[0]
        return {"url": result.get("url", url), "content": result.get("raw_content", "")}


def get_web_tool_client(settings: Settings | None = None) -> WebToolClient | None:
    settings = settings or get_settings()
    if not settings.tavily_api_key:
        return None
    return WebToolClient(api_key=settings.tavily_api_key)
