from __future__ import annotations

import asyncio
import re

import httpx
from fastapi import FastAPI, Request
from structlog.contextvars import bind_contextvars, get_contextvars

from app.middleware import CorrelationIdMiddleware, resolve_correlation_id

ID_FORMAT = re.compile(r"^req-[0-9a-f]{8}$")


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ctx")
    async def ctx(request: Request) -> dict:
        context = dict(get_contextvars())
        bind_contextvars(session_id="leak-me")
        return {"state": request.state.correlation_id, "context": context}

    return app


def _get(app: FastAPI, headers: dict | None = None) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/ctx", headers=headers or {})

    return asyncio.run(send())


def test_generates_id_and_returns_headers() -> None:
    response = _get(_app())
    request_id = response.headers["x-request-id"]
    assert ID_FORMAT.match(request_id)
    assert float(response.headers["x-response-time-ms"]) >= 0
    assert response.json()["state"] == request_id
    assert response.json()["context"]["correlation_id"] == request_id


def test_reuses_valid_incoming_request_id() -> None:
    response = _get(_app(), {"x-request-id": "req-abcdef12"})
    assert response.headers["x-request-id"] == "req-abcdef12"


def test_rejects_malformed_request_id() -> None:
    assert ID_FORMAT.match(resolve_correlation_id("../../etc/passwd"))
    assert ID_FORMAT.match(resolve_correlation_id(None))


def test_context_does_not_leak_between_requests() -> None:
    app = _app()
    first = _get(app)
    second = _get(app)
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert "session_id" not in second.json()["context"]
