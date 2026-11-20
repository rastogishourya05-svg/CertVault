"""Request-level limits apply before multipart parsing or temporary spooling."""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from apps.api.domain import HARD_CAP, STORAGE_HARD_CAP

UPLOAD_LIMIT_MESSAGE = "Certificate exceeds the 100 MiB local demonstration limit"


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path")
        if path == "/account/certificates/upload":
            limit = STORAGE_HARD_CAP + 65536
        elif path == "/account/voice/transcribe":
            limit = 480000
        elif path == "/certificates/upload":
            limit = HARD_CAP + 65536
        else:
            limit = 65536
        try:
            declared = int(dict(scope.get("headers", [])).get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid request length"}, 400)(
                scope, receive, send
            )
        if declared > limit:
            if path == "/account/certificates/upload":
                detail = "Certificate exceeds the 50 MB private Storage limit"
            elif path == "/certificates/upload":
                detail = UPLOAD_LIMIT_MESSAGE
            else:
                detail = "Request exceeds byte limit"
            return await JSONResponse({"detail": detail}, 413)(scope, receive, send)
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
