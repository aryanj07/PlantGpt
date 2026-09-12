"""LLM Gateway Module (plan Section H.1, D).

Generalizes the retry/backoff/circuit-breaker/fallback pattern already
proven client-side in OpenRouterChatRepository/FreeRouterChatRepository
(Flutter lib/features/chat/data/) across every provider, server-side -
closing risk B5 (no retry on the OpenAI path) as a side effect. Streaming
(SSE end-to-end) is a Phase 2 task (plan Section N); V1 always makes one
non-streaming call per route and returns the full text.

RoutingPolicy (plan Section H.1) here is a simple ordered fallback chain
built from which API keys are configured - OpenRouter first, then OpenAI,
matching the Flutter client's existing main.dart priority order so behavior
doesn't surprise anyone migrating off it. Tenant-tier-aware routing and
budget-aware routing are Phase 2+ concerns once the Cost/Quota Module exists.

Cost/token metering (CostMeter in the target design) is a Phase 2 task owned
by the Cost/Quota Module - GatewayReply carries token fields as placeholders
so that module has somewhere to plug in without another interface change.
"""

from dataclasses import dataclass

from app.config import Settings, get_settings
from app.modules.llm_gateway.adapters.base import ProviderAdapter
from app.modules.llm_gateway.adapters.openai_adapter import OpenAiAdapter
from app.modules.llm_gateway.adapters.openrouter_adapter import OpenRouterAdapter
from app.modules.llm_gateway.reliability import CircuitBreaker, ProviderError, call_with_retry

SYSTEM_PROMPT = (
    "You are PlantGPT, a domain expert assistant for industrial plant "
    "operations - cement plants, steel plants, and manufacturing plants. "
    "Help with process parameters, equipment troubleshooting, production-line "
    "optimization, maintenance, and safety questions. Answer clearly, ask "
    "concise follow-up questions when needed, and keep context from the "
    "current chat."
)

HISTORY_LIMIT = 16


@dataclass
class GatewayReply:
    content: str
    model_used: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class _Route:
    def __init__(self, *, name: str, adapter: ProviderAdapter, model: str, max_retries: int = 2) -> None:
        self.name = name
        self.adapter = adapter
        self.model = model
        self.max_retries = max_retries
        self.breaker = CircuitBreaker()


class LLMGateway:
    """Tries each configured route in order; a route that's circuit-open or
    exhausts its retries falls through to the next one. If every route fails,
    returns a graceful-degradation reply rather than raising (plan Section I:
    the user's message is already persisted by the time this runs, so a
    provider outage should never look like data loss)."""

    def __init__(self, routes: list[_Route]) -> None:
        self._routes = routes

    async def generate(self, *, system_prompt: str, history: list[dict], user_message: str) -> GatewayReply:
        if not self._routes:
            return GatewayReply(
                content=(
                    "No LLM provider configured (set OPENAI_API_KEY or OPENROUTER_API_KEY). "
                    f'You said: "{user_message}"'
                ),
                model_used="unconfigured",
            )

        trimmed_history = history[-HISTORY_LIMIT:]
        last_error: ProviderError | None = None

        for route in self._routes:
            if not route.breaker.allow_request():
                continue

            async def _call(route: _Route = route) -> str:
                chunks: list[str] = []
                async for chunk in route.adapter.send(
                    system_prompt=system_prompt or SYSTEM_PROMPT,
                    history=trimmed_history,
                    user_message=user_message,
                    model=route.model,
                    stream=False,
                ):
                    chunks.append(chunk)
                return "".join(chunks)

            try:
                text = await call_with_retry(_call, max_retries=route.max_retries)
                route.breaker.record_success()
                return GatewayReply(content=text, model_used=f"{route.name}:{route.model}")
            except ProviderError as exc:
                route.breaker.record_failure()
                last_error = exc
                continue

        detail = f" ({last_error})" if last_error else ""
        return GatewayReply(content=f"AI temporarily unavailable, your message was saved.{detail}", model_used="degraded")


def build_llm_gateway(settings: Settings | None = None) -> LLMGateway:
    settings = settings or get_settings()
    routes: list[_Route] = []

    if settings.openrouter_api_key:
        routes.append(
            _Route(
                name="openrouter",
                adapter=OpenRouterAdapter(
                    api_key=settings.openrouter_api_key,
                    model=settings.openrouter_model,
                    site_url=settings.openrouter_site_url or None,
                    site_name=settings.openrouter_site_name or None,
                ),
                model=settings.openrouter_model,
            )
        )

    if settings.openai_api_key:
        routes.append(
            _Route(
                name="openai",
                adapter=OpenAiAdapter(api_key=settings.openai_api_key, model=settings.openai_model),
                model=settings.openai_model,
            )
        )

    return LLMGateway(routes)


def get_llm_gateway() -> LLMGateway:
    return build_llm_gateway()
