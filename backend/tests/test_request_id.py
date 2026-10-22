"""Every log line carries the id of the request that wrote it.

Requests run concurrently on one event loop, so the request id must be
per-request state (a ContextVar), never process-global. These tests overlap
requests and check that no line is tagged with another request's id — the
failure mode of a global record factory, where lines picked up whichever
request had set the factory last.
"""

from __future__ import annotations

import asyncio
import logging

import httpx
from fastapi import FastAPI
from main import RequestIdMiddleware, unhandled_exception_handler

_N = 5


def _probe_app() -> FastAPI:
    probe = FastAPI()
    probe.add_middleware(RequestIdMiddleware)
    probe.add_exception_handler(Exception, unhandled_exception_handler)

    @probe.get("/probe/{n}")
    async def probe_route(n: int):
        # Finish in reverse order so every request overlaps the others.
        await asyncio.sleep(0.01 * (_N - n))
        logging.getLogger("probe").info("probe %s", n)
        return {"n": n}

    @probe.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    return probe


async def test_concurrent_requests_keep_their_own_request_id(caplog):
    transport = httpx.ASGITransport(app=_probe_app())
    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                *(
                    client.get(f"/probe/{n}", headers={"X-Request-ID": f"req-{n}"})
                    for n in range(_N)
                )
            )

    assert [r.headers["X-Request-ID"] for r in responses] == [f"req-{n}" for n in range(_N)]
    probe_lines = {r.getMessage(): r.request_id for r in caplog.records if r.name == "probe"}
    assert probe_lines == {f"probe {n}": f"req-{n}" for n in range(_N)}
    access_lines = [r for r in caplog.records if r.name == "main" and "/probe/" in r.getMessage()]
    assert len(access_lines) == _N
    for record in access_lines:
        assert record.getMessage().startswith(f"GET /probe/{record.request_id[-1]} ")


async def test_log_line_outside_a_request_has_no_request_id(caplog):
    with caplog.at_level(logging.INFO):
        logging.getLogger("probe").info("startup")
    assert caplog.records[-1].request_id == "-"


async def test_unhandled_error_is_logged_and_answered_with_the_request_id(caplog):
    transport = httpx.ASGITransport(app=_probe_app(), raise_app_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="main"):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/boom", headers={"X-Request-ID": "req-boom"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-boom"
    errors = [r for r in caplog.records if r.name == "main" and r.levelno == logging.ERROR]
    assert [r.request_id for r in errors] == ["req-boom"]
