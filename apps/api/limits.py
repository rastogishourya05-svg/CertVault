"""Request-level limits apply before multipart parsing or temporary spooling."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.domain import HARD_CAP


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = HARD_CAP + 65536 if scope.get("path") == "/certificates/upload" else 65536
        try:
            declared = int(dict(scope.get("headers", [])).get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid request length"}, 400)(
                scope, receive, send
            )
        if declared > limit:
            return await JSONResponse({"detail": "Request exceeds byte limit"}, 413)(
                scope, receive, send
            )
        observed = 0

        async def bounded_receive():
            nonlocal observed
            message = await receive()
            if message["type"] == "http.request":
                observed += len(message.get("body", b""))
                if observed > limit:
                    raise HTTPException(413, "Request exceeds byte limit")
            return message

        await self.app(scope, bounded_receive, send)
