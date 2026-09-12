"""MCP Tool Broker scaffold (plan Section H.4, D). Phase 4, owner: Rimsha
(RBAC/approval infra) + Prince (tool schema/model-facing design)."""

from enum import Enum


class ToolType(str, Enum):
    READ = "read"
    WRITE = "write"


class MCPToolBroker:
    def dispatch(self, *, tenant_id: str, user_id: str, tool_name: str, arguments: dict) -> dict:
        raise NotImplementedError(
            "Tool dispatch lands in Phase 4. Write tools must never auto-execute "
            "without human approval (plan Section H.4, J.5)."
        )
