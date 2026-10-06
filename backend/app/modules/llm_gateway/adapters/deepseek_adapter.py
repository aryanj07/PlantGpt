"""DeepSeek adapter - third LLM Gateway provider (plan Section O Phase 2:
"Anthropic adapter... third provider in RoutingPolicy", DeepSeek chosen
instead per explicit user request).

DeepSeek's own docs (api-docs.deepseek.com, confirmed live rather than
assumed from training data) describe their API as OpenAI-compatible:
`base_url: https://api.deepseek.com`, Bearer auth, standard chat-completions
request/response shape. This adapter is structurally near-identical to
OpenRouterAdapter as a result - same wire format, same streaming chunk
shape - just a different endpoint/default model and no OpenRouter-specific
attribution headers (HTTP-Referer/X-Title aren't part of the OpenAI spec
DeepSeek claims to match).

Current default model per DeepSeek's docs: "deepseek-flash" (their primary
general-purpose model as of this writing; "deepseek-v4-pro" is their
higher-end tier - override via DEEPSEEK_MODEL if you want that instead).
"""

import json
from collections.abc import AsyncIterator

import httpx

from app.modules.llm_gateway.adapters.base import ProviderAdapter
from app.modules.llm_gateway.reliability import ProviderError

CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"


class DeepSeekAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient()
        self._timeout = timeout
        # Set by the most recent send() call, read by the Gateway's
        # Cost/Quota Module after a successful reply (plan Section H.1) -
        # None if the response never included usage data.
        self.last_usage: dict[str, int] | None = None

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

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
            raise ProviderError(provider="deepseek", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="deepseek", detail=str(exc), is_transient=True) from exc

        _raise_for_status(response.status_code)

        data = response.json()
        self.last_usage = _normalize_usage(data.get("usage"))
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(provider="deepseek", detail="empty choices", is_transient=False)

        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise ProviderError(provider="deepseek", detail="empty content", is_transient=False)
        yield content

    async def _send_streaming(self, body: dict, headers: dict) -> AsyncIterator[str]:
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
            raise ProviderError(provider="deepseek", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="deepseek", detail=str(exc), is_transient=True) from exc


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
        raise ProviderError(provider="deepseek", detail="rate limited", is_transient=True, status_code=429)
    if status_code in (502, 503, 504):
        raise ProviderError(
            provider="deepseek", detail="provider failure", is_transient=True, status_code=status_code
        )
    if status_code in (401, 403):
        raise ProviderError(provider="deepseek", detail="auth failure", is_transient=False, status_code=status_code)
    raise ProviderError(
        provider="deepseek",
        detail=detail or f"request failed with status {status_code}",
        is_transient=False,
        status_code=status_code,
    )
