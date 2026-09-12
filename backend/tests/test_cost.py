"""Tests for the Cost/Quota Module (plan Section D, G.1, H.1, O Phase 2 DoD:
"Simulated over-budget tenant correctly rejected"). Covers the tracker in
isolation, usage recording from a real (mocked) provider response, the
non-streaming endpoint's 402 hard-stop, the streaming endpoint's SSE error
equivalent, and the usage-visibility endpoint.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.modules.cost.store import ledger
from app.modules.cost.tracker import BudgetExceededError, CostTracker
from app.modules.llm_gateway.adapters.openrouter_adapter import OpenRouterAdapter
from app.modules.llm_gateway.gateway import LLMGateway, _Route

client = TestClient(app)
HEADERS = {"X-Dev-Tenant-Id": "budget-tenant", "X-Dev-User-Id": "u1"}


@pytest.fixture(autouse=True)
def _clear_ledger():
    ledger._usage.clear()
    yield
    ledger._usage.clear()


def _tracker(budget_usd: float = 1.0) -> CostTracker:
    settings = Settings(default_monthly_budget_usd=budget_usd)
    return CostTracker(settings=settings)


def test_check_budget_allows_a_fresh_tenant() -> None:
    _tracker(budget_usd=1.0).check_budget(tenant_id="fresh-tenant")  # must not raise


def test_record_computes_cost_from_pricing_table() -> None:
    tracker = _tracker(budget_usd=10.0)
    tracker.record(tenant_id="t1", model="gpt-5", prompt_tokens=1_000_000, completion_tokens=1_000_000)

    snapshot = tracker.snapshot(tenant_id="t1")
    assert snapshot.tokens_used == 2_000_000
    assert snapshot.cost_usd == pytest.approx(5.00 + 15.00)


def test_free_model_never_exhausts_budget() -> None:
    tracker = _tracker(budget_usd=0.01)
    tracker.record(
        tenant_id="t1", model="openrouter/free", prompt_tokens=1_000_000, completion_tokens=1_000_000
    )
    tracker.check_budget(tenant_id="t1")  # must not raise - $0 cost


def test_over_budget_tenant_is_rejected() -> None:
    tracker = _tracker(budget_usd=0.01)
    tracker.record(tenant_id="t1", model="gpt-5", prompt_tokens=10_000, completion_tokens=10_000)

    with pytest.raises(BudgetExceededError):
        tracker.check_budget(tenant_id="t1")


def test_unknown_model_falls_back_to_default_pricing() -> None:
    tracker = _tracker(budget_usd=100.0)
    tracker.record(tenant_id="t1", model="some-new-model", prompt_tokens=1_000_000, completion_tokens=0)
    snapshot = tracker.snapshot(tenant_id="t1")
    assert snapshot.cost_usd == pytest.approx(10.00)  # DEFAULT_PRICING_USD_PER_1M_TOKENS prompt rate


@pytest.mark.anyio
async def test_non_streaming_call_records_usage_and_then_hard_stops() -> None:
    from fastapi import HTTPException

    from app.modules.chat import service as chat_service

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "reply"}}],
                "usage": {"prompt_tokens": 10_000, "completion_tokens": 10_000, "total_tokens": 20_000},
            },
        )

    adapter = OpenRouterAdapter(
        api_key="k", model="gpt-5", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    gateway = LLMGateway([_Route(name="openrouter", adapter=adapter, model="gpt-5")])
    tracker = _tracker(budget_usd=0.01)  # cheap enough that one reply exhausts it

    conv = client.post("/v1/conversations", headers=HEADERS).json()

    _, assistant_msg = await chat_service.post_user_message(
        tenant_id="budget-tenant",
        conversation_id=conv["id"],
        content="hi",
        llm_gateway=gateway,
        cost_tracker=tracker,
    )
    assert assistant_msg.content == "reply"
    assert tracker.snapshot(tenant_id="budget-tenant").cost_usd > 0

    # The next call must be hard-stopped before it ever reaches the gateway.
    with pytest.raises(HTTPException) as exc_info:
        await chat_service.post_user_message(
            tenant_id="budget-tenant",
            conversation_id=conv["id"],
            content="hi again",
            llm_gateway=gateway,
            cost_tracker=tracker,
        )
    assert exc_info.value.status_code == 402


def test_streaming_endpoint_reports_budget_exceeded_as_sse_error() -> None:
    conv = client.post("/v1/conversations", headers=HEADERS).json()

    # Pre-exhaust the budget for this tenant directly in the shared ledger
    # (same object the endpoint's default get_cost_tracker() reads from).
    usage = ledger.get_or_create("budget-tenant")
    usage.cost_usd = 999.0

    response = client.post(
        f"/v1/conversations/{conv['id']}/messages/stream",
        headers=HEADERS,
        json={"content": "hi"},
    )

    assert response.status_code == 200
    events = [
        json.loads(block[len("data:") :].strip())
        for block in response.text.split("\n\n")
        if block.strip().startswith("data:")
    ]
    assert events[0]["type"] == "user_message"
    assert events[1]["type"] == "error"
    assert "budget" in events[1]["detail"].lower()
    assert events[-1]["type"] == "done"


def test_usage_endpoint_reports_current_snapshot() -> None:
    usage = ledger.get_or_create("budget-tenant")
    usage.tokens_used = 42
    usage.cost_usd = 0.005

    response = client.get("/v1/cost/usage", headers=HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "budget-tenant"
    assert body["tokens_used"] == 42
    assert body["cost_usd"] == pytest.approx(0.005)
    assert body["remaining_usd"] == pytest.approx(body["budget_usd"] - 0.005)
