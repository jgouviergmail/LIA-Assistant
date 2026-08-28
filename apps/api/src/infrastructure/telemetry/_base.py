"""Shared HTTP plumbing for telemetry clients.

One place implements the "reading never raises" contract:

- an empty base URL short-circuits to ``("disabled", None)``;
- the whole call runs inside the source's circuit breaker (an open circuit
  short-circuits without any HTTP request);
- transport errors, non-2xx statuses and malformed JSON all collapse into
  ``(reason, None)`` — the concrete clients turn that into their typed
  ``unavailable`` result.

Clients create one ``httpx.AsyncClient`` per call on purpose: call rates are
low (5-minute self-check cadence plus rare admin queries), so pooling would
buy nothing while a shared client would need an owner tied to one event loop
across four uvicorn workers (async-ownership rule).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from src.infrastructure.resilience.circuit_breaker import (
    CircuitBreakerError,
    get_circuit_breaker,
)

logger = structlog.get_logger(__name__)

#: Circuit-breaker service-name prefix for telemetry sources.
TELEMETRY_BREAKER_PREFIX = "telemetry_"


class TelemetryHTTPBase:
    """Base class carrying the guarded GET helper for telemetry clients."""

    #: Breaker suffix; concrete clients override ("prometheus", "loki", ...).
    source_name: str = "unknown"

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Store connection parameters.

        Args:
            base_url: Source base URL; empty string means the source is
                disabled and every call reports ``unavailable("disabled")``.
            timeout_seconds: Per-request timeout applied to the whole call.
            transport: Optional httpx transport override (tests inject a
                ``MockTransport`` here; production leaves it None).
        """
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def _guarded_get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> tuple[str | None, Any]:
        """GET ``base_url + path`` and parse JSON, under the circuit breaker.

        Args:
            path: URL path starting with '/'.
            params: Optional query parameters.

        Returns:
            ``(None, payload)`` on success, ``(reason, None)`` on any failure
            — this method never raises.
        """
        if not self._base_url:
            return "disabled", None

        breaker = get_circuit_breaker(f"{TELEMETRY_BREAKER_PREFIX}{self.source_name}")
        try:
            async with breaker:
                async with httpx.AsyncClient(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.get(f"{self._base_url}{path}", params=params)
                    response.raise_for_status()
                    return None, json.loads(response.content)
        except CircuitBreakerError:
            return "circuit_open", None
        except httpx.HTTPStatusError as exc:
            reason = f"http_{exc.response.status_code}"
        except httpx.HTTPError as exc:
            reason = f"transport:{type(exc).__name__}"
        except json.JSONDecodeError, UnicodeDecodeError:
            reason = "malformed_json"
        logger.debug(
            "telemetry_source_unavailable",
            source=self.source_name,
            reason=reason,
        )
        return reason, None
