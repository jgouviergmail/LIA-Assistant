"""Prometheus read client (instant queries only, never raises).

Only the named-query catalogue (`domains/diagnostics/query_catalogue.py`) may
produce the PromQL passed here — free-form query text must never reach this
client from an LLM (spec §5, pillar 1).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.infrastructure.telemetry._base import TelemetryHTTPBase
from src.infrastructure.telemetry.models import PromResult, PromSample


class PrometheusClient(TelemetryHTTPBase):
    """Bounded read access to the Prometheus HTTP API."""

    source_name = "prometheus"

    async def instant_query(self, promql: str) -> PromResult:
        """Run an instant query and parse its vector (or scalar) result.

        Args:
            promql: A catalogue-rendered PromQL expression.

        Returns:
            PromResult with status 'ok' and samples, or 'unavailable'.
        """
        reason, payload = await self._guarded_get_json(
            "/api/v1/query",
            params={"query": promql},
        )
        if reason is not None:
            return PromResult(status="unavailable", error=reason)
        try:
            return PromResult(status="ok", samples=_parse_vector(payload))
        except KeyError, TypeError, ValueError, IndexError:
            return PromResult(status="unavailable", error="unexpected_shape")


def _parse_vector(payload: Any) -> list[PromSample]:
    """Parse an instant-query response body into samples.

    Args:
        payload: Decoded JSON body of /api/v1/query.

    Returns:
        Vector samples (scalar results become a single unlabelled sample).

    Raises:
        KeyError, TypeError, ValueError, IndexError: On unexpected shapes —
            the caller converts these into an 'unavailable' result.
    """
    if payload["status"] != "success":
        raise ValueError("prometheus_status_not_success")
    data = payload["data"]
    result_type = data["resultType"]
    if result_type == "scalar":
        ts_raw, value_raw = data["result"]
        return [
            PromSample(
                metric={},
                value=float(value_raw),
                ts=datetime.fromtimestamp(float(ts_raw), tz=UTC),
            )
        ]
    if result_type != "vector":
        raise ValueError(f"unsupported_result_type:{result_type}")
    samples: list[PromSample] = []
    for entry in data["result"]:
        ts_raw, value_raw = entry["value"]
        samples.append(
            PromSample(
                metric={str(k): str(v) for k, v in entry["metric"].items()},
                value=float(value_raw),
                ts=datetime.fromtimestamp(float(ts_raw), tz=UTC),
            )
        )
    return samples
