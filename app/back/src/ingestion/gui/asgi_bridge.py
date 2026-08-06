"""Serve an ASGI application from the existing ``http.server`` GUI backend.

The phase-1 GUI is a plain ``ThreadingHTTPServer``. Rather than hand-writing one
router bridge per domain, this adapter forwards a request into any ASGI app, so
the FastAPI routers stay the single definition of the HTTP contract (and of the
published OpenAPI document).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class AsgiResponse:
    """One buffered ASGI response."""

    status: int
    headers: dict[str, str]
    body: bytes


class AsgiBridge:
    """Call an ASGI application synchronously from a blocking HTTP handler."""

    def __init__(self, app: Any) -> None:
        self._app = app

    def handle(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes = b"",
    ) -> AsgiResponse:
        """Forward one request into the ASGI app and buffer the response."""

        return asyncio.run(self._call(method=method, path=path, headers=headers, body=body))

    async def _call(
        self,
        *,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> AsgiResponse:
        parsed = urlparse(path)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method.upper(),
            "scheme": "http",
            "path": parsed.path,
            "raw_path": parsed.path.encode("utf-8"),
            "query_string": parsed.query.encode("utf-8"),
            "root_path": "",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
            "client": ("127.0.0.1", 0),
            "server": ("127.0.0.1", 8765),
        }
        request_sent = False

        async def receive() -> dict[str, object]:
            nonlocal request_sent
            if request_sent:
                return {"type": "http.disconnect"}
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        status = 500
        response_headers: dict[str, str] = {}
        chunks: list[bytes] = []

        async def send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
                response_headers.update(
                    {
                        name.decode("latin-1"): value.decode("latin-1")
                        for name, value in message.get("headers", [])
                    }
                )
            elif message["type"] == "http.response.body":
                chunks.append(bytes(message.get("body", b"")))

        await self._app(scope, receive, send)
        return AsgiResponse(
            status=status,
            headers=response_headers,
            body=b"".join(chunks),
        )
