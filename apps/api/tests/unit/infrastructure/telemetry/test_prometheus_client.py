"""PrometheusClient — bounded instant queries that never raise.

The doctrine under test: whatever the backend does (5xx, timeout, garbage,
open circuit, disabled source), the caller receives a typed result with
``status="unavailable"`` — never an exception.
"""

from __future__ import annotations

from datetime import UTC

import httpx
import pytest

from src.infrastructure.resilience.circuit_breaker import get_circuit_breaker
from src.infrastructure.telemetry.prometheus import PrometheusClient
from tests.unit.infrastructure.telemetry.conftest import (
    transport_raising,
    transport_returning,
    transport_returning_text,
)

_VECTOR_PAYLOAD = {
    "status": "success",
    "data": {
        "resultType": "vector",
        "result": [
            {
                "metric": {"job": "lia-api", "status": "500"},
                "value": [1724800000.123, "0.25"],
            },
            {"metric": {"job": "lia-api", "status": "200"}, "value": [1724800000.123, "4.5"]},
        ],
    },
}


@pytest.mark.unit
class TestPrometheusClient:
    async def test_nominal_vector_parse(self) -> None:
        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=transport_returning(_VECTOR_PAYLOAD),
        )
        result = await client.instant_query("up")
        assert result.status == "ok"
        assert len(result.samples) == 2
        first = result.samples[0]
        assert first.metric == {"job": "lia-api", "status": "500"}
        assert first.value == pytest.approx(0.25)
        assert first.ts.tzinfo is UTC

    async def test_server_error_is_unavailable_not_raise(self) -> None:
        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=transport_returning({"status": "error"}, status_code=500),
        )
        result = await client.instant_query("up")
        assert result.status == "unavailable"
        assert result.samples == []
        assert result.error is not None

    async def test_timeout_is_unavailable_not_raise(self) -> None:
        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=transport_raising(httpx.ConnectTimeout("boom")),
        )
        result = await client.instant_query("up")
        assert result.status == "unavailable"

    async def test_malformed_json_is_unavailable_not_raise(self) -> None:
        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=transport_returning_text("<html>not json</html>"),
        )
        result = await client.instant_query("up")
        assert result.status == "unavailable"

    async def test_empty_base_url_means_disabled_source(self) -> None:
        client = PrometheusClient(base_url="", timeout_seconds=2.0)
        result = await client.instant_query("up")
        assert result.status == "unavailable"
        assert result.error == "disabled"

    async def test_open_circuit_short_circuits_without_http_call(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json=_VECTOR_PAYLOAD)

        breaker = get_circuit_breaker("telemetry_prometheus")
        for _ in range(breaker.failure_threshold):
            await breaker.record_failure(RuntimeError("induced"))

        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=httpx.MockTransport(handler),
        )
        result = await client.instant_query("up")
        assert result.status == "unavailable"
        assert calls["n"] == 0

    async def test_failures_open_the_circuit(self) -> None:
        client = PrometheusClient(
            base_url="http://prometheus:9090",
            timeout_seconds=2.0,
            transport=transport_raising(httpx.ConnectError("down")),
        )
        breaker = get_circuit_breaker("telemetry_prometheus")
        for _ in range(breaker.failure_threshold):
            await client.instant_query("up")
        assert breaker.get_status()["state"] == "open"
