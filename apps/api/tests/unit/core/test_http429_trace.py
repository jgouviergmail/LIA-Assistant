"""HTTP throttling remains attributable when ordinary access logs are quiet."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Scope

from src.core import middleware
from src.core.client_ip import resolve_client_ip

pytestmark = pytest.mark.unit

_CLIENT_IP = "198.51.100.44"


@pytest.fixture(autouse=True)
def _http_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(middleware.settings, "http_log_level", "DEBUG")
    monkeypatch.setattr(middleware.settings, "http_log_exclude_paths", ["/health"])
    monkeypatch.setattr(middleware.settings, "rate_limit_enabled", True)
    monkeypatch.setattr(middleware.settings, "rate_limit_global_per_minute", 300)


@pytest.fixture
def log_output(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """Capture real structured output behind the production INFO threshold."""
    output = io.StringIO()
    target = logging.Logger("test.http429.trace", level=logging.INFO)
    handler = logging.StreamHandler(output)
    target.addHandler(handler)
    bound_logger = structlog.wrap_logger(
        target,
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    monkeypatch.setattr(middleware, "logger", bound_logger)
    try:
        yield output
    finally:
        target.removeHandler(handler)
        handler.close()


def _events(output: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.getvalue().splitlines()]


def _app(status_code: int, *, global_limit: bool = False) -> ASGIApp:
    async def endpoint(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "endpoint"}, status_code=status_code)

    app: ASGIApp = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST"])])
    if global_limit:
        app = middleware.RateLimitMiddleware(app)
    return middleware.RequestIDMiddleware(middleware.LoggingMiddleware(app))


def test_global_429_logs_trusted_ip_and_warning_completion(
    monkeypatch: pytest.MonkeyPatch, log_output: io.StringIO
) -> None:
    class RefusingLimiter:
        async def acquire(self, key: str, max_calls: int, window_seconds: int) -> bool:
            return False

    async def get_limiter() -> RefusingLimiter:
        return RefusingLimiter()

    monkeypatch.setattr(middleware, "get_rate_limiter", get_limiter)
    with TestClient(_app(200, global_limit=True)) as client:
        response = client.get(
            "/api/v1/chat",
            headers={"CF-Connecting-IP": _CLIENT_IP, "X-Forwarded-For": "127.0.0.1"},
        )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    events = _events(log_output)
    rejected = next(event for event in events if event["event"] == "global_rate_limit_exceeded")
    assert rejected["client_ip"] == _CLIENT_IP
    completed = [event for event in events if event["event"] == "request_completed"]
    assert len(completed) == 1
    assert completed[0]["level"] == "warning"
    assert completed[0]["status_code"] == 429
    assert completed[0]["client_ip"] == _CLIENT_IP
    assert completed[0]["request_id"] == rejected["request_id"]


@pytest.mark.parametrize("path", ["/api/v1/limited", "/health"])
def test_endpoint_429_survives_info_and_path_exclusion(path: str, log_output: io.StringIO) -> None:
    with TestClient(_app(429)) as client:
        response = client.get(path, headers={"CF-Connecting-IP": _CLIENT_IP})

    assert response.status_code == 429
    completed = [event for event in _events(log_output) if event["event"] == "request_completed"]
    assert len(completed) == 1
    event = completed[0]
    assert event["level"] == "warning"
    assert event["status_code"] == 429
    assert event["client_ip"] == _CLIENT_IP
    assert event["method"] == "GET"
    assert event["path"] == path
    assert isinstance(event["duration_ms"], int | float)
    assert event["duration_ms"] >= 0


def test_429_trace_contains_no_query_body_cookie_or_authorization(log_output: io.StringIO) -> None:
    with TestClient(_app(429)) as client:
        response = client.post(
            "/api/v1/limited?token=query-secret-marker&text=query-content-marker",
            json={"password": "body-secret-marker"},
            headers={
                "CF-Connecting-IP": _CLIENT_IP,
                "Authorization": "Bearer authorization-secret-marker",
                "Cookie": "session=cookie-secret-marker",
            },
        )

    assert response.status_code == 429
    events = _events(log_output)
    assert len(events) == 1
    assert events[0]["event"] == "request_completed"
    assert events[0]["path"] == "/api/v1/limited"
    assert events[0]["method"] == "POST"
    assert set(events[0]) <= {
        "event",
        "level",
        "request_id",
        "geo_country",
        "geo_city",
        "path",
        "method",
        "status_code",
        "duration_ms",
        "client_ip",
    }
    for secret in (
        "query-secret-marker",
        "query-content-marker",
        "body-secret-marker",
        "authorization-secret-marker",
        "cookie-secret-marker",
    ):
        assert secret not in log_output.getvalue()


def test_429_completion_reuses_the_request_ip_resolution(
    monkeypatch: pytest.MonkeyPatch, log_output: io.StringIO
) -> None:
    resolved: list[Scope] = []

    def resolve(scope: Scope) -> str:
        resolved.append(scope)
        return resolve_client_ip(scope)

    monkeypatch.setattr(middleware, "resolve_client_ip", resolve)
    with TestClient(_app(429)) as client:
        response = client.get("/limited", headers={"CF-Connecting-IP": _CLIENT_IP})

    assert response.status_code == 429
    assert len(resolved) == 1
    assert len(_events(log_output)) == 1


@pytest.mark.parametrize("status_code", [200, 400, 503])
def test_other_statuses_keep_debug_visibility(status_code: int, log_output: io.StringIO) -> None:
    with TestClient(_app(status_code)) as client:
        response = client.get("/endpoint", headers={"CF-Connecting-IP": _CLIENT_IP})

    assert response.status_code == status_code
    assert _events(log_output) == []


def test_other_statuses_keep_configured_info_shape(
    monkeypatch: pytest.MonkeyPatch, log_output: io.StringIO
) -> None:
    monkeypatch.setattr(middleware.settings, "http_log_level", "INFO")
    with TestClient(_app(200)) as client:
        response = client.get("/endpoint", headers={"CF-Connecting-IP": _CLIENT_IP})

    assert response.status_code == 200
    events = _events(log_output)
    assert [event["event"] for event in events] == ["request_started", "request_completed"]
    assert all(event["level"] == "info" for event in events)
    assert "client_ip" not in events[-1]
