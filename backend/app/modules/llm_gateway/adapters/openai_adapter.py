"""Server-side port of the Flutter OpenAiChatRepository
(lib/features/chat/data/openai_chat_repository.dart): same endpoint
(OpenAI Responses API), same 'developer'-role system prompt convention, same
max_output_tokens=1200. Retry/backoff/circuit-breaker are NOT reimplemented
here - they're generalized once in llm_gateway/reliability.py and applied by
the Gateway to every adapter uniformly, closing plan risk B5 (the Flutter
version of this repository had no retry at all).
"""

from collections.abc import AsyncIterator

import httpx

from app.modules.llm_gateway.adapters.base import ProviderAdapter
from app.modules.llm_gateway.reliability import ProviderError

RESPONSES_URL = "https://api.openai.com/v1/responses"


class OpenAiAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 45.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient()
        self._timeout = timeout

    async def send(
        self, *, system_prompt: str, history: list[dict], user_message: str, model: str, stream: bool
    ) -> AsyncIterator[str]:
        # V1 is non-streaming end to end (plan Section N Phase 2 adds real
        # streaming) - always makes one call and yields the full text once.
        input_messages = [{"role": "developer", "content": system_prompt}]
        input_messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        input_messages.append({"role": "user", "content": user_message})

        body = {"model": model or self._model, "input": input_messages, "max_output_tokens": 1200}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        try:
            response = await self._client.post(
                RESPONSES_URL, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openai", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openai", detail=str(exc), is_transient=True) from exc

        if response.status_code == 429:
            raise ProviderError(provider="openai", detail="rate limited", is_transient=True, status_code=429)
        if response.status_code in (502, 503, 504):
            raise ProviderError(
                provider="openai", detail="provider failure", is_transient=True, status_code=response.status_code
            )
        if response.status_code != 200:
            raise ProviderError(
                provider="openai",
                detail=f"request failed with status {response.status_code}",
                is_transient=False,
                status_code=response.status_code,
            )

        text = _extract_output_text(response.json())
        if not text:
            raise ProviderError(provider="openai", detail="empty response", is_transient=False)
        yield text


def _extract_output_text(data: dict) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text:
        return output_text

    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)
    return "".join(chunks)
