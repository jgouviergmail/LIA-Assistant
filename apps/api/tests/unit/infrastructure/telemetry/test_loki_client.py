"""LokiClient — bounded LogQL range queries that never raise."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from src.infrastructure.telemetry.loki import LokiClient
from tests.unit.infrastructure.telemetry.conftest import (
    transport_raising,
    transport_returning,
)

_LINE = json.dumps({"event": "chat_run_failed", "level": "error", "run_id": "r1"})
_STREAMS_PAYLOAD = {
    "status": "success",
    "data": {
        "resultType": "streams",
        "result": [
            {
                "stream": {"container": "lia-api-prod", "level": "error", "service": "api"},
                "values": [
                    ["1724800000123456789", _LINE],
                    ["1724800001123456789", "plain text line"],
                ],
            }
        ],
    },
}


def _window() -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(hours=1), end


@pytest.mark.unit
class TestLokiClient:
    async def test_nominal_streams_parse(self) -> None:
        client = LokiClient(
            base_url="http://loki:3100",
            timeout_seconds=2.0,
            transport=transport_returning(_STREAMS_PAYLOAD),
        )
        start, end = _window()
        result = await client.query_range('{service="api"}', start=start, end=end, limit=100)
        assert result.status == "ok"
        assert len(result.lines) == 2
        # Contract: newest first — the plain line has the later timestamp.
        plain, structured = result.lines
        assert structured.payload == {"event": "chat_run_failed", "level": "error", "run_id": "r1"}
        assert structured.container == "lia-api-prod"
        assert structured.level == "error"
        assert structured.ts.tzinfo is UTC
        assert plain.payload is None
        assert plain.raw == "plain text line"

    async def test_query_params_carry_bounds(self) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return httpx.Response(200, json=_STREAMS_PAYLOAD)

        client = LokiClient(
            base_url="http://loki:3100",
            timeout_seconds=2.0,
            transport=httpx.MockTransport(handler),
        )
        start, end = _window()
        await client.query_range('{service="api"}', start=start, end=end, limit=42)
        assert seen["limit"] == "42"
        assert seen["query"] == '{service="api"}'
        # Loki takes nanosecond epochs; both bounds must be present and ordered.
        assert int(seen["start"]) < int(seen["end"])

    async def test_backend_error_is_unavailable(self) -> None:
        client = LokiClient(
            base_url="http://loki:3100",
            timeout_seconds=2.0,
            transport=transport_raising(httpx.ReadTimeout("slow")),
        )
        start, end = _window()
        result = await client.query_range('{service="api"}', start=start, end=end, limit=10)
        assert result.status == "unavailable"
        assert result.lines == []

    async def test_empty_base_url_means_disabled_source(self) -> None:
        client = LokiClient(base_url="", timeout_seconds=2.0)
        start, end = _window()
        result = await client.query_range('{service="api"}', start=start, end=end, limit=10)
        assert result.status == "unavailable"
        assert result.error == "disabled"
