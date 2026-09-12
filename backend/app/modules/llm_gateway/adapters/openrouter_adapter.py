"""Server-side port of the Flutter OpenRouterChatRepository
(lib/features/chat/data/open_router_chat_repository.dart): same endpoint
(OpenRouter.ai's Chat Completions-compatible API), same optional
HTTP-Referer/X-Title attribution headers. Retry/backoff/circuit-breaker are
NOT reimplemented here - they're generalized once in
llm_gateway/reliability.py and applied by the Gateway to every adapter
uniformly (the retry/backoff formula itself is the one this adapter's
Flutter counterpart already proved out).

Image/multimodal forwarding (the one capability this repository had that
OpenAI's didn't) is not ported yet - the Chat module doesn't accept image
uploads server-side yet either, so there's nothing to forward.
"""

from collections.abc import AsyncIterator

import httpx

from app.modules.llm_gateway.adapters.base import ProviderAdapter
from app.modules.llm_gateway.reliability import ProviderError

CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        site_url: str | None = None,
        site_name: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient()
        self._timeout = timeout
        self._site_url = site_url
        self._site_name = site_name

    async def send(
        self, *, system_prompt: str, history: list[dict], user_message: str, model: str, stream: bool
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        messages.append({"role": "user", "content": user_message})

        body = {"model": model or self._model, "messages": messages}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_name:
            headers["X-Title"] = self._site_name

        try:
            response = await self._client.post(
                CHAT_COMPLETIONS_URL, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openrouter", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openrouter", detail=str(exc), is_transient=True) from exc

        if response.status_code == 429:
            raise ProviderError(
                provider="openrouter", detail="rate limited", is_transient=True, status_code=429
            )
        if response.status_code in (502, 503, 504):
            raise ProviderError(
                provider="openrouter",
                detail="provider failure",
                is_transient=True,
                status_code=response.status_code,
            )
        if response.status_code in (401, 403):
            raise ProviderError(
                provider="openrouter", detail="auth failure", is_transient=False, status_code=response.status_code
            )
        if response.status_code != 200:
            raise ProviderError(
                provider="openrouter",
                detail=f"request failed with status {response.status_code}",
                is_transient=False,
                status_code=response.status_code,
            )

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(provider="openrouter", detail="empty choices", is_transient=False)

        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise ProviderError(provider="openrouter", detail="empty content", is_transient=False)
        yield content
