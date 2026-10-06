"""MCP Tool Broker (plan Section H.4, D). Phase 4.

Dispatch is heuristic, not LLM function-calling (plan decision, this
session): RequestRouter already decides *that* a tool is needed and
classify_tool_kind() decides *which* one - run() below is what
chat/service.py actually calls. dispatch(tool_name, arguments) stays as a
stub for a possible future real function-calling migration; nothing calls
it yet.

v1 ships zero WRITE tools (search, scrape, and the sensor simulator are all
READ), which is what lets it skip the human-approval flow this module's
ToolType.WRITE implies (plan Section H.4, J.5) - not an oversight, a scope
choice to revisit only once a real write tool is actually proposed.
"""

import re
from dataclasses import dataclass
from enum import Enum

from app.modules.mcp.tools.sensor_simulator import simulate_reading
from app.modules.mcp.tools.web_tool import WebToolClient, get_web_tool_client
from app.modules.router.classifier import ToolKind, classify_tool_kind

_URL_RE = re.compile(r"https?://\S+")


class ToolType(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass
class ToolResult:
    # Prepended to the LLM Gateway's system prompt, same shape as RAG's
    # context block (chat/service.py's _build_context_prompt).
    context_text: str
    # Same {"document_id", "title", "source_uri"} shape RAG citations use -
    # the Flutter "Source: ..." UI needs no changes to show these too.
    citations: list[dict]


class MCPToolBroker:
    def __init__(self, *, web_client: WebToolClient | None = None) -> None:
        self._web_client = web_client

    def dispatch(self, *, tenant_id: str, user_id: str, tool_name: str, arguments: dict) -> dict:
        raise NotImplementedError(
            "Not used - this project dispatches tools heuristically via run(), "
            "not LLM-chosen tool_name/arguments (plan Section H.4). Write tools "
            "must never auto-execute without human approval (J.5) if this is "
            "ever implemented for real function-calling."
        )

    async def run(self, *, query: str) -> ToolResult | None:
        kind = classify_tool_kind(query)
        if kind == ToolKind.SENSOR:
            return self._run_sensor(query)
        if kind == ToolKind.WEB_SEARCH:
            return await self._run_web_search(query)
        return await self._run_web_extract(query)

    def _run_sensor(self, query: str) -> ToolResult:
        reading = simulate_reading(query)
        if reading["metric"] is None:
            text = (
                "[Simulated plant data tool] No live data source is connected "
                "for this request in this demo environment - say so plainly, "
                "don't invent a specific number."
            )
        else:
            text = (
                f"[Simulated plant data tool - NOT a real live reading] "
                f"{reading['metric']}: {reading['value']} {reading['unit']} "
                f"(as of {reading['as_of']}). Make clear to the user this is "
                f"simulated demo data, not a live plant reading."
            )
        citation = {
            "document_id": f"sensor:{reading['metric'] or 'unknown'}",
            "title": "Simulated sensor reading",
            "source_uri": None,
        }
        return ToolResult(context_text=text, citations=[citation])

    async def _run_web_search(self, query: str) -> ToolResult | None:
        client = self._web_client or get_web_tool_client()
        if client is None:
            raise RuntimeError("Web search requested but TAVILY_API_KEY isn't configured.")

        results = await client.search(query)
        if not results:
            return None

        excerpts = "\n\n".join(f"[{r['title']}]({r['url']})\n{r['content']}" for r in results)
        text = f"[External web search results - not internal plant documentation]\n\n{excerpts}"
        citations = [{"document_id": r["url"], "title": r["title"], "source_uri": r["url"]} for r in results]
        return ToolResult(context_text=text, citations=citations)

    async def _run_web_extract(self, query: str) -> ToolResult | None:
        match = _URL_RE.search(query)
        if match is None:
            return None

        client = self._web_client or get_web_tool_client()
        if client is None:
            raise RuntimeError("Page extraction requested but TAVILY_API_KEY isn't configured.")

        result = await client.extract(match.group(0))
        if result is None:
            return None

        text = f"[External web page content - not internal plant documentation]\n\n{result['content']}"
        citation = {"document_id": result["url"], "title": result["url"], "source_uri": result["url"]}
        return ToolResult(context_text=text, citations=[citation])


def get_mcp_tool_broker() -> MCPToolBroker:
    return MCPToolBroker()
