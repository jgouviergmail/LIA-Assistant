"""Loki read client (bounded range queries, never raises).

Only the constrained builder (`domains/diagnostics/logql.py`) may produce the
LogQL passed here; the builder clamps range and line count to the hard caps in
``src.core.constants`` because Loki on the Pi has an OOM history (see the
measured commentary in infrastructure/observability/promtail/promtail-config.yml).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.infrastructure.telemetry._base import TelemetryHTTPBase
from src.infrastructure.telemetry.models import LokiLine, LokiResult

_NANOSECONDS_PER_SECOND = 1_000_000_000


class LokiClient(TelemetryHTTPBase):
    """Bounded read access to the Loki HTTP API."""

    source_name = "loki"

    async def query_range(
        self,
        logql: str,
        *,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> LokiResult:
        """Run a bounded range query, newest lines first.

        Args:
            logql: A builder-produced LogQL expression.
            start: Aware range start.
            end: Aware range end.
            limit: Max lines (the builder already clamped it to the hard cap).

        Returns:
            LokiResult with status 'ok' and lines, or 'unavailable'.
        """
        reason, payload = await self._guarded_get_json(
            "/loki/api/v1/query_range",
            params={
                "query": logql,
                "start": str(int(start.timestamp() * _NANOSECONDS_PER_SECOND)),
                "end": str(int(end.timestamp() * _NANOSECONDS_PER_SECOND)),
                "limit": str(limit),
                "direction": "backward",
            },
        )
        if reason is not None:
            return LokiResult(status="unavailable", error=reason)
        try:
            return LokiResult(status="ok", lines=_parse_streams(payload))
        except KeyError, TypeError, ValueError:
            return LokiResult(status="unavailable", error="unexpected_shape")


def _parse_streams(payload: Any) -> list[LokiLine]:
    """Parse a query_range response into lines (newest first, all streams).

    Args:
        payload: Decoded JSON body of /loki/api/v1/query_range.

    Returns:
        Log lines with the structlog JSON payload parsed when the line is JSON.

    Raises:
        KeyError, TypeError, ValueError: On unexpected shapes — the caller
            converts these into an 'unavailable' result.
    """
    if payload["status"] != "success":
        raise ValueError("loki_status_not_success")
    data = payload["data"]
    if data["resultType"] != "streams":
        raise ValueError(f"unsupported_result_type:{data['resultType']}")
    lines: list[LokiLine] = []
    for stream in data["result"]:
        labels = stream.get("stream", {})
        for ts_ns_raw, raw_line in stream["values"]:
            parsed: dict[str, object] | None
            try:
                candidate = json.loads(raw_line)
                parsed = candidate if isinstance(candidate, dict) else None
            except json.JSONDecodeError, UnicodeDecodeError:
                parsed = None
            lines.append(
                LokiLine(
                    ts=datetime.fromtimestamp(int(ts_ns_raw) / _NANOSECONDS_PER_SECOND, tz=UTC),
                    container=str(labels.get("container", "")),
                    level=str(labels.get("level", "")),
                    payload=parsed,
                    raw=raw_line,
                )
            )
    lines.sort(key=lambda line: line.ts, reverse=True)
    return lines
