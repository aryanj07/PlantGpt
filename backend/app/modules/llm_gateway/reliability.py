"""Generalized reliability primitives shared by every ProviderAdapter (plan
Section H.1, I). This is the one place that implements retry/backoff and
circuit-breaker logic - adapters only classify their own errors as transient
or not; they never retry or track breaker state themselves.

The backoff formula (300ms * 2^attempt + 0-199ms jitter, max 2 retries)
matches what was already proven client-side in
OpenRouterChatRepository/FreeRouterChatRepository (Flutter
lib/features/chat/data/) - ported here rather than reinvented, and now
applied uniformly across every provider (closing plan risk B5: the OpenAI
path previously had no retry at all).

Circuit-breaker state here is in-process, per adapter instance, per API
worker. That's correct for a single instance; once there's more than one API
instance (plan Section F, ~100-user tier) this needs to move to Redis-backed
shared state (plan ADR 3) so instances agree on whether a provider is open -
that migration is a Phase 5 (Reliability & Observability) task, not this one.
"""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from enum import Enum

DEFAULT_BASE_DELAY_MS = 300
DEFAULT_JITTER_MS = 200


class ProviderError(Exception):
    def __init__(
        self, *, provider: str, detail: str, is_transient: bool, status_code: int | None = None
    ) -> None:
        super().__init__(f"{provider}: {detail}")
        self.provider = provider
        self.detail = detail
        self.is_transient = is_transient
        self.status_code = status_code


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int = 5, cooldown_seconds: float = 30.0) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self._cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()


async def call_with_retry(
    fn: Callable[[], Awaitable[str]],
    *,
    max_retries: int = 2,
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS,
    jitter_ms: int = DEFAULT_JITTER_MS,
) -> str:
    attempt = 0
    while True:
        try:
            return await fn()
        except ProviderError as exc:
            if not exc.is_transient or attempt >= max_retries:
                raise
            delay_seconds = (base_delay_ms * (2**attempt) + random.randint(0, jitter_ms)) / 1000
            await asyncio.sleep(delay_seconds)
            attempt += 1
