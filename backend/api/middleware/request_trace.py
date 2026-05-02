from __future__ import annotations

from time import monotonic

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.common.errors import AgentError
from backend.common.logging import bound_log_context, get_logger, new_trace_id

TRACE_HEADER = "X-Trace-Id"
logger = get_logger(component="request_trace")


class RequestTraceError(AgentError):
    pass


class RequestTraceMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = _trace_id_from_request(request)
        started_at = monotonic()
        with bound_log_context(
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
        ):
            try:
                response = await call_next(request)
                response.headers[TRACE_HEADER] = trace_id
                logger.debug(
                    "http_request_end",
                    status_code=response.status_code,
                    duration_ms=int((monotonic() - started_at) * 1000),
                )
                return response
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "http_request_error",
                    duration_ms=int((monotonic() - started_at) * 1000),
                )
                raise RequestTraceError("REQUEST_TRACE_ERROR", str(exc)) from exc


def _trace_id_from_request(request: Request) -> str:
    value = request.headers.get(TRACE_HEADER, "").strip()
    return value or new_trace_id()


__all__ = ["RequestTraceError", "RequestTraceMiddleware", "TRACE_HEADER"]
