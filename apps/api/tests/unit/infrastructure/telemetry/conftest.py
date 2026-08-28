"""Shared fixtures for telemetry client tests.

Every test gets a pristine circuit-breaker registry: breakers are global
singletons keyed by service name, so state from one test (an opened circuit)
must never leak into the next.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry


@pytest.fixture(autouse=True)
def _clean_breakers() -> Iterator[None]:
    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


def transport_returning(payload: Any, status_code: int = 200) -> httpx.MockTransport:
    """A transport answering every request with one canned JSON response."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=json.dumps(payload).encode())

    return httpx.MockTransport(handler)


def transport_raising(exc: Exception) -> httpx.MockTransport:
    """A transport raising the given exception on every request."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return httpx.MockTransport(handler)


def transport_returning_text(text: str, status_code: int = 200) -> httpx.MockTransport:
    """A transport answering with a non-JSON body (malformed-payload cases)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=text.encode())

    return httpx.MockTransport(handler)
