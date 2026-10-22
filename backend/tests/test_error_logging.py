"""One failure, one log entry.

The catch-all handler in main.py logs an unhandled exception with its
traceback. Starlette then re-raises it and the server would log the same
traceback again (uvicorn: "Exception in ASGI application"; Mangum on
serverless hosting: "An error occurred running the application."), so
log-based error monitoring would count every failing request twice. These
tests pin that the handler marks what it logged and that the server's
duplicate is dropped — and only that duplicate.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from main import _AlreadyLoggedFilter, unhandled_exception_handler
from starlette.requests import Request


def _request() -> Request:
    return Request(
        {"type": "http", "method": "POST", "path": "/api/tasks", "headers": [], "query_string": b""}
    )


def _uvicorn_record(exc: BaseException | None) -> logging.LogRecord:
    exc_info = (type(exc), exc, exc.__traceback__) if exc is not None else None
    return logging.LogRecord(
        "uvicorn.error",
        logging.ERROR,
        __file__,
        0,
        "Exception in ASGI application\n",
        None,
        exc_info,
    )


def test_handler_logs_once_and_answers_500(caplog):
    exc = RuntimeError("boom")
    with caplog.at_level(logging.ERROR, logger="main"):
        response = asyncio.run(unhandled_exception_handler(_request(), exc))

    assert response.status_code == 500
    logged = [r for r in caplog.records if r.name == "main" and r.exc_info]
    assert len(logged) == 1
    assert logged[0].exc_info[1] is exc


def test_uvicorn_duplicate_of_a_handled_exception_is_dropped():
    exc = RuntimeError("boom")
    asyncio.run(unhandled_exception_handler(_request(), exc))
    assert _AlreadyLoggedFilter().filter(_uvicorn_record(exc)) is False


def test_exception_the_handler_never_saw_is_still_logged():
    assert _AlreadyLoggedFilter().filter(_uvicorn_record(RuntimeError("escaped"))) is True
    assert _AlreadyLoggedFilter().filter(_uvicorn_record(None)) is True


@pytest.mark.parametrize("logger_name", ["uvicorn.error", "mangum.http"])
def test_filter_is_installed_on_the_server_error_loggers(logger_name):
    filters = logging.getLogger(logger_name).filters
    assert any(isinstance(f, _AlreadyLoggedFilter) for f in filters)
