"""Server-side port of the Flutter OpenRouterChatRepository
(lib/features/chat/data/open_router_chat_repository.dart): same endpoint
(OpenRouter.ai's Chat Completions-compatible API), same optional
HTTP-Referer/X-Title attribution headers. Retry/backoff/circuit-breaker are
NOT reimplemented here - they're generalized once in
llm_gateway/reliability.py and applied by the Gateway to every adapter
uniformly (the retry/backoff formula itself is the one this adapter's
Flutter counterpart already proved out).

Streaming (stream=True, plan ADR 5 / Phase 2) uses the standard OpenAI-
compatible chat-completions SSE format: each chunk is
{"choices":[{"delta":{"content":"..."}}]}, terminated by a literal
"data: [DONE]" line.

Image/multimodal forwarding (the one capability this repository had that
OpenAI's didn't) is not ported yet - the Chat module doesn't accept image
uploads server-side yet either, so there's nothing to forward.
"""

import json
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
        # Set by the most recent send() call, read by the Gateway's
        # Cost/Quota Module after a successful reply (plan Section H.1) -
        # None if the response never included usage data.
        self.last_usage: dict[str, int] | None = None

    def _headers(self) -> dict:
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url
        if self._site_name:
            headers["X-Title"] = self._site_name
        return headers

    async def send(
        self, *, system_prompt: str, history: list[dict], user_message: str, model: str, stream: bool
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        messages.append({"role": "user", "content": user_message})

        body = {"model": model or self._model, "messages": messages}
        headers = self._headers()

        if stream:
            async for chunk in self._send_streaming(body, headers):
                yield chunk
            return

        try:
            response = await self._client.post(
                CHAT_COMPLETIONS_URL, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openrouter", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openrouter", detail=str(exc), is_transient=True) from exc

        _raise_for_status(response.status_code)

        data = response.json()
        self.last_usage = _normalize_usage(data.get("usage"))
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(provider="openrouter", detail="empty choices", is_transient=False)

        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise ProviderError(provider="openrouter", detail="empty content", is_transient=False)
        yield content

    async def _send_streaming(self, body: dict, headers: dict) -> AsyncIterator[str]:
        # include_usage asks for one extra final chunk carrying token counts
        # (empty choices, top-level usage) - standard OpenAI-compatible
        # stream_options, which OpenRouter proxies through.
        stream_body = {**body, "stream": True, "stream_options": {"include_usage": True}}
        try:
            async with self._client.stream(
                "POST", CHAT_COMPLETIONS_URL, json=stream_body, headers=headers, timeout=self._timeout
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    _raise_for_status(response.status_code, detail=error_body.decode(errors="replace")[:300])

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if not payload or payload == "[DONE]":
                        continue

                    chunk = json.loads(payload)
                    usage = chunk.get("usage")
                    if usage:
                        self.last_usage = _normalize_usage(usage)
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openrouter", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openrouter", detail=str(exc), is_transient=True) from exc


def _normalize_usage(usage: dict | None) -> dict[str, int] | None:
    if not usage:
        return None
    return {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _raise_for_status(status_code: int, *, detail: str | None = None) -> None:
    if status_code == 200:
        return
    if status_code == 429:
        raise ProviderError(provider="openrouter", detail="rate limited", is_transient=True, status_code=429)
    if status_code in (502, 503, 504):
        raise ProviderError(
            provider="openrouter", detail="provider failure", is_transient=True, status_code=status_code
        )
    if status_code in (401, 403):
        raise ProviderError(provider="openrouter", detail="auth failure", is_transient=False, status_code=status_code)
    raise ProviderError(
        provider="openrouter",
        detail=detail or f"request failed with status {status_code}",
        is_transient=False,
        status_code=status_code,
    )
