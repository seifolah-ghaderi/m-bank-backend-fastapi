import json
import logging
import traceback
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from app.core.dates import business_timezone

logger = logging.getLogger("crm.requests")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


class RequestContextMiddleware:
    def __init__(self, app, timezone: str):
        self.app = app
        self.timezone = timezone

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            request_id = str(UUID(Headers(scope=scope).get("x-request-id", "")))
        except ValueError:
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        zone_token = business_timezone.set(self.timezone)
        started = False
        status = 500
        error_start = None
        error_body = bytearray()

        async def traced_send(message):
            nonlocal started, status, error_start
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
                status = message["status"]
                if status >= 400:
                    error_start = message
                    return
                started = True
            if message["type"] == "http.response.body" and error_start is not None:
                error_body.extend(message.get("body", b""))
                if message.get("more_body", False):
                    return
                try:
                    payload = json.loads(error_body)
                    assert isinstance(payload.get("error"), dict)
                except (ValueError, AttributeError, AssertionError):
                    payload = {
                        "error": {
                            "code": "request_error",
                            "message": "Request rejected",
                            "details": [],
                            "request_id": request_id,
                        }
                    }
                payload["error"]["request_id"] = request_id
                response = JSONResponse(payload, status_code=status)
                for key, value in error_start["headers"]:
                    if key not in {b"content-length", b"content-type"}:
                        response.raw_headers.append((key, value))
                started = True
                await response(scope, receive, send)
                return
            await send(message)

        try:
            await self.app(scope, receive, traced_send)
        except Exception as error:
            if started:
                raise
            logger.error(
                json.dumps(
                    {
                        "request_id": request_id,
                        "error_type": type(error).__name__,
                        "stack": [
                            f"{frame.filename}:{frame.lineno}:{frame.name}"
                            for frame in traceback.extract_tb(error.__traceback__)
                        ],
                    }
                )
            )
            response = JSONResponse(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "Internal server error",
                        "details": [],
                        "request_id": request_id,
                    }
                },
                status_code=500,
            )
            await response(scope, receive, traced_send)
        finally:
            logger.info(
                json.dumps({"request_id": request_id, "method": scope["method"], "status": status})
            )
            business_timezone.reset(zone_token)
