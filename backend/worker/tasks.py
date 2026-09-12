"""Arq task stubs (plan Section D, N Phase 3+). Real ingestion (Phase 3) and
MCP write-follow-up (Phase 4) jobs land here. This exists so the queue wiring
has a home before there's real work to run."""


async def example_task(ctx: dict, message: str) -> str:
    return f"processed: {message}"
