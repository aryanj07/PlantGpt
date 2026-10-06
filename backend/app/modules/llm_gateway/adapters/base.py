"""ProviderAdapter interface (plan Section H.1)."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class ProviderAdapter(ABC):
    @abstractmethod
    async def send(
        self,
        *,
        system_prompt: str,
        history: list[dict],
        user_message: str,
        model: str,
        stream: bool,
    ) -> AsyncIterator[str]:
        """Yield response text chunks (a single chunk if stream=False).

        history entries are {"role": "user"|"assistant", "content": str} -
        each adapter builds its own provider-specific request shape from
        these neutral parts (OpenAI's Responses API and OpenRouter's Chat
        Completions API disagree on the system-role name and the top-level
        field, so there is no single shared "messages" list to hand them).
        """
        raise NotImplementedError
        yield  # pragma: no cover - makes this an async generator for type-checkers
