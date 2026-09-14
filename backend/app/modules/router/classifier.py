"""RequestRouter v1 (plan Section H.3): a single deterministic, testable
classification function - explicitly not a graph/agent loop. At this team's
size an explicit router is easier to debug/test than a framework's internal
control flow, and the actual behavior needed (classify -> optionally
retrieve -> optionally call bounded tools -> answer) doesn't require one.

Deliberately a cheap heuristic (keyword/phrase matching), not a model call -
"explicit rules take precedence over model judgement where possible" (plan
H.3). Revisit only if the tool surface grows large enough that hand-rolled
routing genuinely becomes the bottleneck.

Wiring status: RAGService.retrieve() (Phase 3) and MCPToolBroker.run()
(Phase 4) are both real now - chat/service.py branches on this
classification to compose the context it sends to the LLM Gateway, for
both the RAG half and the tool half.
"""

import re
from enum import Enum


class Route(str, Enum):
    SIMPLE_CHAT = "SIMPLE_CHAT"
    NEEDS_RAG = "NEEDS_RAG"
    NEEDS_TOOL = "NEEDS_TOOL"
    NEEDS_RAG_AND_TOOL = "NEEDS_RAG_AND_TOOL"


class ToolKind(str, Enum):
    """Which MCP tool a NEEDS_TOOL/NEEDS_RAG_AND_TOOL query maps to (plan
    Section H.4). A second, narrower classification rather than new Route
    values - Route stays about "does the LLM need extra context", ToolKind
    is only consulted once that's already yes, so adding tools doesn't
    combinatorially explode Route."""

    SENSOR = "SENSOR"
    WEB_SEARCH = "WEB_SEARCH"
    WEB_EXTRACT = "WEB_EXTRACT"


# Hand-maintained phrase lists, lowercase substring matching - simple by
# design (plan H.3). Extend these rather than reaching for a model call.
_TOOL_PHRASES = [
    "current temperature", "currently running", "current reading",
    "current vibration", "current pressure", "current status",
    "right now", "live sensor", "live reading", "real-time", "real time",
    "today's production", "today's output", "active alarm", "any alarms",
    "work order", "is online", "is offline", "gone offline",
    "is down", "is running",
    # Web search/scrape (Phase 4) - a different tool than the live-plant-data
    # phrases above, but still just "needs a tool" at the Route level;
    # classify_tool_kind() below is what tells them apart.
    "search the web", "look up online", "find online", "latest news on",
]
_RAG_PHRASES = [
    "our sop", "our policy", "our plant's policy", "our documentation",
    "the manual", "the maintenance manual", "the equipment manual",
    "according to the manual", "according to our", "the documentation",
    "maintenance sop", "the procedure for", "specified in the manual",
    "torque spec", "spec sheet", "safety policy", "emergency shutdown sequence",
]

_URL_RE = re.compile(r"https?://\S+")
_WEB_SEARCH_PHRASES = ["search the web", "look up online", "find online", "latest news on"]


def classify(query: str) -> Route:
    q = query.lower()
    needs_tool = any(phrase in q for phrase in _TOOL_PHRASES)
    needs_rag = any(phrase in q for phrase in _RAG_PHRASES)

    if needs_tool and needs_rag:
        return Route.NEEDS_RAG_AND_TOOL
    if needs_tool:
        return Route.NEEDS_TOOL
    if needs_rag:
        return Route.NEEDS_RAG
    return Route.SIMPLE_CHAT


def classify_tool_kind(query: str) -> ToolKind:
    """Only meaningful when classify() already returned a tool-needing
    route. A URL wins outright (the user clearly wants that page scraped);
    otherwise a web-search phrase; otherwise SENSOR - which also covers
    phrases like "work order" or "current status" that don't name a real
    simulated metric, since sensor_simulator.simulate_reading() itself
    replies honestly ("no live data source for this") rather than
    fabricating a number for something it doesn't actually simulate.
    """
    if _URL_RE.search(query):
        return ToolKind.WEB_EXTRACT
    q = query.lower()
    if any(phrase in q for phrase in _WEB_SEARCH_PHRASES):
        return ToolKind.WEB_SEARCH
    return ToolKind.SENSOR
