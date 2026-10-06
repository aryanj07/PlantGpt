"""Request/trace id propagation (plan Section K).

This is deliberately minimal for Phase 0: generate/accept request_id and
trace_id, attach them to request.state and the response headers, and make
them available to logging. Full OpenTelemetry export to a managed backend is
a Phase 5 task (ADR 11) — this module is the seam that work plugs into.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("plantgpt")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        trace_id = request.headers.get("x-trace-id", request_id)

        request.state.request_id = request_id
        request.state.trace_id = trace_id
        # tenant_id/user_id are attached by the Auth Module dependency once a
        # request has been authenticated (plan Section K.1) — not known yet here.

        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Trace-Id"] = trace_id
        return response
