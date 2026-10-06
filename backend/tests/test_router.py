"""Tests for RequestRouter v1 (plan Section H.3, O Phase 2 DoD: "Minimal
eval set (~30 labeled cases) matches expected_route"). The golden set below
mirrors plan Section L's eval_case shape (query -> expected_route) scoped
down to just this classifier - 35 hand-labeled, domain-realistic queries
covering all four routes.
"""

import pytest

from app.modules.router.classifier import Route, ToolKind, classify, classify_tool_kind

GOLDEN_CASES: list[tuple[str, Route]] = [
    # SIMPLE_CHAT - general domain knowledge, nothing live or plant-specific
    ("What is a normal kiln burning-zone temperature?", Route.SIMPLE_CHAT),
    ("Explain how a rotary kiln works.", Route.SIMPLE_CHAT),
    ("What causes clinker nodulization?", Route.SIMPLE_CHAT),
    ("What's the difference between wet and dry process cement production?", Route.SIMPLE_CHAT),
    ("How often should conveyor belts generally be inspected?", Route.SIMPLE_CHAT),
    ("What safety gear is typically required near a blast furnace?", Route.SIMPLE_CHAT),
    ("Why does steel need to be annealed?", Route.SIMPLE_CHAT),
    ("What's a typical cause of bearing failure in industrial motors?", Route.SIMPLE_CHAT),
    ("Hello, can you help me with plant operations questions?", Route.SIMPLE_CHAT),
    ("What does OEE stand for?", Route.SIMPLE_CHAT),
    # NEEDS_TOOL - asking for live/real-time plant data
    ("What is the current temperature of kiln 2?", Route.NEEDS_TOOL),
    ("Is the crusher currently running?", Route.NEEDS_TOOL),
    ("Are there any active alarms on line 3?", Route.NEEDS_TOOL),
    ("What's today's production output so far?", Route.NEEDS_TOOL),
    ("Show me the live sensor reading for the boiler.", Route.NEEDS_TOOL),
    ("What's the status of work order 4521?", Route.NEEDS_TOOL),
    ("Is conveyor belt 7 online right now?", Route.NEEDS_TOOL),
    ("Give me the real-time pressure reading on the reactor.", Route.NEEDS_TOOL),
    ("Has the furnace gone offline today?", Route.NEEDS_TOOL),
    ("What is the current vibration reading on pump 12?", Route.NEEDS_TOOL),
    # NEEDS_RAG - plant-specific documents/policy
    ("According to our SOP, how do we handle a kiln shutdown?", Route.NEEDS_RAG),
    ("What does the maintenance manual say about lubrication intervals?", Route.NEEDS_RAG),
    ("What is our plant's policy on confined-space entry?", Route.NEEDS_RAG),
    ("Can you check the documentation for the crusher's spec sheet?", Route.NEEDS_RAG),
    ("What's the procedure for our emergency shutdown sequence?", Route.NEEDS_RAG),
    ("According to the manual, what's the torque spec for this bolt?", Route.NEEDS_RAG),
    ("What does our safety policy say about PPE near the furnace?", Route.NEEDS_RAG),
    ("Summarize the maintenance sop for changeover on line 2.", Route.NEEDS_RAG),
    ("What's specified in the equipment manual for this motor?", Route.NEEDS_RAG),
    ("Does the documentation cover this specific valve?", Route.NEEDS_RAG),
    # NEEDS_RAG_AND_TOOL - both a document lookup and live data
    (
        "According to our SOP, what should I do if kiln 2's current temperature is too high?",
        Route.NEEDS_RAG_AND_TOOL,
    ),
    (
        "Check the maintenance manual for the alarm threshold, then tell me if line 3 currently "
        "has an active alarm.",
        Route.NEEDS_RAG_AND_TOOL,
    ),
    (
        "Per the maintenance sop, is pump 12's current vibration reading within spec?",
        Route.NEEDS_RAG_AND_TOOL,
    ),
    (
        "What does our safety policy say to do if the crusher is currently running unattended?",
        Route.NEEDS_RAG_AND_TOOL,
    ),
    (
        "According to the manual, what's the procedure now that work order 4521's status shows "
        "overdue?",
        Route.NEEDS_RAG_AND_TOOL,
    ),
]


@pytest.mark.parametrize("query,expected_route", GOLDEN_CASES, ids=[c[0][:40] for c in GOLDEN_CASES])
def test_classify_matches_expected_route(query: str, expected_route: Route) -> None:
    assert classify(query) == expected_route


def test_golden_set_accuracy_meets_dod_threshold() -> None:
    """The Phase 2 DoD is "matches expected_route" against the golden set -
    asserted per-case above; this also reports an aggregate so a future
    rule tweak that regresses accuracy fails loudly with a number, not just
    a list of which individual cases broke."""
    correct = sum(1 for query, expected in GOLDEN_CASES if classify(query) == expected)
    accuracy = correct / len(GOLDEN_CASES)
    assert accuracy == 1.0, f"router accuracy {accuracy:.0%} on the {len(GOLDEN_CASES)}-case golden set"


def test_classify_is_deterministic() -> None:
    query = "According to our SOP, what should I do if kiln 2's current temperature is too high?"
    assert classify(query) == classify(query) == Route.NEEDS_RAG_AND_TOOL


TOOL_KIND_CASES: list[tuple[str, ToolKind]] = [
    ("What is the current temperature of kiln 2?", ToolKind.SENSOR),
    ("What's the status of work order 4521?", ToolKind.SENSOR),
    ("Search the web for the latest cement industry emissions regulations.", ToolKind.WEB_SEARCH),
    ("Can you look up online what causes clinker nodulization?", ToolKind.WEB_SEARCH),
    ("Summarize https://example.com/plant-safety-bulletin for me.", ToolKind.WEB_EXTRACT),
]


@pytest.mark.parametrize("query,expected_kind", TOOL_KIND_CASES, ids=[c[0][:40] for c in TOOL_KIND_CASES])
def test_classify_tool_kind_matches_expected(query: str, expected_kind: ToolKind) -> None:
    assert classify_tool_kind(query) == expected_kind


def test_classify_tool_kind_prefers_url_over_web_search_phrase() -> None:
    query = "Search the web using https://example.com/report as a starting point."
    assert classify_tool_kind(query) == ToolKind.WEB_EXTRACT
