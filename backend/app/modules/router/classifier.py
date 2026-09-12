"""RequestRouter v1 (plan Section H.3): a single deterministic, testable
classification function - explicitly not a graph/agent loop. At this team's
size an explicit router is easier to debug/test than a framework's internal
control flow, and the actual behavior needed (classify -> optionally
retrieve -> optionally call bounded tools -> answer) doesn't require one.

Deliberately a cheap heuristic (keyword/phrase matching), not a model call -
"explicit rules take precedence over model judgement where possible" (plan
H.3). Revisit only if the tool surface grows large enough that hand-rolled
routing genuinely becomes the bottleneck.

Wiring status: RAGService.retrieve() and MCPToolBroker.dispatch() are still
Phase 3/4 stubs (raise NotImplementedError), so nothing branches execution
on this classification yet - chat/service.py calls classify() and logs the
result for observability/preparation only. The TODO at that call site marks
exactly where Phase 3/4 adds real conditional dispatch.
"""

from enum import Enum


class Route(str, Enum):
    SIMPLE_CHAT = "SIMPLE_CHAT"
    NEEDS_RAG = "NEEDS_RAG"
    NEEDS_TOOL = "NEEDS_TOOL"
    NEEDS_RAG_AND_TOOL = "NEEDS_RAG_AND_TOOL"


# Hand-maintained phrase lists, lowercase substring matching - simple by
# design (plan H.3). Extend these rather than reaching for a model call.
_TOOL_PHRASES = [
    "current temperature", "currently running", "current reading",
    "current vibration", "current pressure", "current status",
    "right now", "live sensor", "live reading", "real-time", "real time",
    "today's production", "today's output", "active alarm", "any alarms",
    "work order", "is online", "is offline", "gone offline",
    "is down", "is running",
]
_RAG_PHRASES = [
    "our sop", "our policy", "our plant's policy", "our documentation",
    "the manual", "the maintenance manual", "the equipment manual",
    "according to the manual", "according to our", "the documentation",
    "maintenance sop", "the procedure for", "specified in the manual",
    "torque spec", "spec sheet", "safety policy", "emergency shutdown sequence",
]


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
