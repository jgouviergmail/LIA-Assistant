"""Read access to LIA's own telemetry backends (spec 2026-08-27).

Clients never raise on a caller's path: every failure mode collapses into a
typed result with ``status="unavailable"`` (see ``models``). Query text always
comes from the constrained producers in ``domains/diagnostics`` — never from
free-form (or LLM-authored) strings.
"""

from src.infrastructure.telemetry.alertmanager import AlertmanagerClient
from src.infrastructure.telemetry.loki import LokiClient
from src.infrastructure.telemetry.models import (
    ActiveAlert,
    AlertsResult,
    LokiLine,
    LokiResult,
    PromResult,
    PromSample,
    TelemetryStatus,
)
from src.infrastructure.telemetry.prometheus import PrometheusClient

__all__ = [
    "ActiveAlert",
    "AlertmanagerClient",
    "AlertsResult",
    "LokiClient",
    "LokiLine",
    "LokiResult",
    "PromResult",
    "PromSample",
    "PrometheusClient",
    "TelemetryStatus",
]
