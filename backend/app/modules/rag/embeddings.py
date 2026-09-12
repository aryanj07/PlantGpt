"""OpenAI embeddings client (Phase 3 plan's embeddings ADR: text-embedding-3-small).
Same httpx + ProviderError pattern as llm_gateway/adapters/openai_adapter.py -
reused deliberately rather than reinvented, even though embeddings aren't
part of the LLM Gateway's chat routing (there's no "fallback provider" for
embeddings in V1 - if OpenAI is down, ingestion/retrieval fail loudly rather
than silently degrading, since a wrong/missing embedding is worse than none).
"""

from collections.abc import Sequence

import httpx

from app.config import Settings, get_settings
from app.modules.llm_gateway.reliability import ProviderError

EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small's native output size


class EmbeddingsClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient()
        self._timeout = timeout

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        body = {"model": self._model, "input": list(texts)}

        try:
            response = await self._client.post(
                EMBEDDINGS_URL, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openai-embeddings", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openai-embeddings", detail=str(exc), is_transient=True) from exc

        if response.status_code == 429:
            raise ProviderError(
                provider="openai-embeddings", detail="rate limited", is_transient=True, status_code=429
            )
        if response.status_code in (502, 503, 504):
            raise ProviderError(
                provider="openai-embeddings",
                detail="provider failure",
                is_transient=True,
                status_code=response.status_code,
            )
        if response.status_code != 200:
            raise ProviderError(
                provider="openai-embeddings",
                detail=f"request failed with status {response.status_code}: {response.text[:300]}",
                is_transient=False,
                status_code=response.status_code,
            )

        data = response.json()
        # OpenAI returns entries in the same order as the input, each
        # carrying its own `index` - sort defensively rather than assume.
        entries = sorted(data.get("data", []), key=lambda e: e.get("index", 0))
        return [entry["embedding"] for entry in entries]


def get_embeddings_client(settings: Settings | None = None) -> EmbeddingsClient:
    settings = settings or get_settings()
    return EmbeddingsClient(api_key=settings.openai_api_key, model=settings.embedding_model)
