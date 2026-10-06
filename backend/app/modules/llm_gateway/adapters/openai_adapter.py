"""Server-side port of the Flutter OpenAiChatRepository
(lib/features/chat/data/openai_chat_repository.dart): same endpoint
(OpenAI Responses API), same 'developer'-role system prompt convention, same
max_output_tokens=1200. Retry/backoff/circuit-breaker are NOT reimplemented
here - they're generalized once in llm_gateway/reliability.py and applied by
the Gateway to every adapter uniformly, closing plan risk B5 (the Flutter
version of this repository had no retry at all).

Streaming (stream=True, plan ADR 5 / Phase 2) uses the Responses API's SSE
event stream directly rather than faking incremental delivery - event
shapes confirmed against openai-python's generated types
(response_text_delta_event.py / response_completed_event.py): each text
chunk arrives as {"type": "response.output_text.delta", "delta": "..."},
terminated by {"type": "response.completed", ...}.
"""

import json
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
        # Set by the most recent send() call, read by the Gateway's
        # Cost/Quota Module after a successful reply (plan Section H.1) -
        # None if the response never included usage data.
        self.last_usage: dict[str, int] | None = None

    async def send(
        self, *, system_prompt: str, history: list[dict], user_message: str, model: str, stream: bool
    ) -> AsyncIterator[str]:
        input_messages = [{"role": "developer", "content": system_prompt}]
        input_messages.extend({"role": m["role"], "content": m["content"]} for m in history)
        input_messages.append({"role": "user", "content": user_message})

        body = {"model": model or self._model, "input": input_messages, "max_output_tokens": 1200}
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

        if stream:
            async for chunk in self._send_streaming(body, headers):
                yield chunk
            return

        try:
            response = await self._client.post(
                RESPONSES_URL, json=body, headers=headers, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openai", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openai", detail=str(exc), is_transient=True) from exc

        _raise_for_status(response.status_code)

        data = response.json()
        self.last_usage = _normalize_usage(data.get("usage"))
        text = _extract_output_text(data)
        if not text:
            raise ProviderError(provider="openai", detail="empty response", is_transient=False)
        yield text

    async def _send_streaming(self, body: dict, headers: dict) -> AsyncIterator[str]:
        stream_body = {**body, "stream": True}
        try:
            async with self._client.stream(
                "POST", RESPONSES_URL, json=stream_body, headers=headers, timeout=self._timeout
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    _raise_for_status(response.status_code, detail=error_body.decode(errors="replace")[:300])

                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:") :].strip()
                    if not payload:
                        continue

                    event = json.loads(payload)
                    event_type = event.get("type")

                    if event_type == "response.output_text.delta":
                        delta = event.get("delta")
                        if delta:
                            yield delta
                    elif event_type in ("response.failed", "response.incomplete", "error"):
                        raise ProviderError(
                            provider="openai",
                            detail=f"stream error: {json.dumps(event)[:300]}",
                            is_transient=True,
                        )
                    elif event_type == "response.completed":
                        self.last_usage = _normalize_usage(
                            (event.get("response") or {}).get("usage")
                        )
                        return
        except httpx.TimeoutException as exc:
            raise ProviderError(provider="openai", detail="request timed out", is_transient=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(provider="openai", detail=str(exc), is_transient=True) from exc


def _raise_for_status(status_code: int, *, detail: str | None = None) -> None:
    if status_code == 200:
        return
    if status_code == 429:
        raise ProviderError(provider="openai", detail="rate limited", is_transient=True, status_code=429)
    if status_code in (502, 503, 504):
        raise ProviderError(provider="openai", detail="provider failure", is_transient=True, status_code=status_code)
    raise ProviderError(
        provider="openai",
        detail=detail or f"request failed with status {status_code}",
        is_transient=False,
        status_code=status_code,
    )


def _normalize_usage(usage: dict | None) -> dict[str, int] | None:
    """OpenAI's Responses API names these input_tokens/output_tokens -
    normalized to the same {prompt_tokens, completion_tokens, total_tokens}
    shape the Cost/Quota Module expects from every adapter."""
    if not usage:
        return None
    return {
        "prompt_tokens": usage.get("input_tokens", 0),
        "completion_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


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
