"""The constrained LogQL builder: the ONLY producer of LogQL in the subsystem.

Injection is closed by construction — service is a closed enum (the compose
``service`` label, identical in dev and prod), level a closed set, the event
name a strict structlog-shaped pattern. Range and line count are CLAMPED to
the hard caps in ``src.core.constants`` because Loki on the Pi has an OOM
history (measured commentary in promtail-config.yml): what is mechanically
repairable is repaired; what cannot be repaired without inventing intent
(an invalid event name, an unknown level) is rejected (ADR-184 doctrine).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from src.core.constants import (
    DIAGNOSTICS_LOKI_MAX_LINES,
    DIAGNOSTICS_LOKI_MAX_RANGE_HOURS,
)

#: structlog levels as promoted to the Loki ``level`` label.
ALLOWED_LEVELS: frozenset[str] = frozenset({"debug", "info", "warning", "error", "critical"})

_EVENT_NAME_RE = re.compile(r"^[a-z0-9_.]{1,64}$")


class DiagService(str, Enum):
    """Compose services whose logs may be queried (the ``service`` label)."""

    API = "api"
    WEB = "web"
    POSTGRES = "postgres"
    REDIS = "redis"
    PROMETHEUS = "prometheus"
    LOKI = "loki"
    PROMTAIL = "promtail"
    GRAFANA = "grafana"
    ALERTMANAGER = "alertmanager"
    TEMPO = "tempo"
    POSTGRES_BACKUP = "postgres-backup"


@dataclass(frozen=True)
class BoundedLogQuery:
    """A ready-to-run, already-clamped Loki range query."""

    logql: str
    start: datetime
    end: datetime
    limit: int


def build_log_query(
    service: DiagService,
    level: str = "",
    event: str = "",
    minutes: int = 60,
    limit: int = DIAGNOSTICS_LOKI_MAX_LINES,
    *,
    end: datetime | None = None,
) -> BoundedLogQuery:
    """Build a bounded LogQL query for one service.

    Args:
        service: Target compose service (closed enum).
        level: Optional level filter (closed set; empty = all levels).
        event: Optional structlog event name (strict pattern; empty = none).
        minutes: Look-back window; clamped to the hard range cap.
        limit: Line budget; clamped into [1, hard cap] (default: the cap).
        end: Range end (defaults to now, UTC).

    Returns:
        BoundedLogQuery carrying the LogQL string and the clamped bounds.

    Raises:
        ValueError: Unknown service type, unknown level, or invalid event name
            — unrepairable without inventing intent.
    """
    if not isinstance(service, DiagService):
        raise ValueError(f"service must be a DiagService, got {type(service).__name__}")
    if level and level not in ALLOWED_LEVELS:
        raise ValueError(f"unknown level '{level}' (allowed: {sorted(ALLOWED_LEVELS)})")
    if event and not _EVENT_NAME_RE.fullmatch(event):
        raise ValueError("event must match ^[a-z0-9_.]{1,64}$")

    clamped_minutes = min(max(int(minutes), 1), DIAGNOSTICS_LOKI_MAX_RANGE_HOURS * 60)
    clamped_limit = min(max(int(limit), 1), DIAGNOSTICS_LOKI_MAX_LINES)
    range_end = end if end is not None else datetime.now(UTC)
    range_start = range_end - timedelta(minutes=clamped_minutes)

    selector = f'{{service="{service.value}"'
    if level:
        selector += f', level="{level}"'
    selector += "}"
    logql = selector
    if event:
        logql += f' | json | event="{event}"'
    return BoundedLogQuery(logql=logql, start=range_start, end=range_end, limit=clamped_limit)
