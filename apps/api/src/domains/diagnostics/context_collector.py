"""The evidence pack a diagnostician reads, fetched AT DIAGNOSIS time (ADR-266).

What the model received until 2026-09-05 was seven fields, and four diagnoses
out of four ended in "insufficient evidence" while Prometheus held the breakdown
(two failed operations out of eight, both ``http_500``) and Loki held the failing
path (every failure on ``rag_injection_failed``). This module fetches exactly
what the incident's recipe declares — catalogue queries and named log events,
never a free-form expression — and shapes it into a small, JSON-serialisable,
PII-free pack.

Three properties, each a decision:

- **Fail-open by source.** Every source degrades to ``status: "unavailable"``
  on its own and the runtime block is always present, so a Loki outage costs a
  diagnosis its log excerpt, never the diagnosis (ADR-247: telemetry reading
  never raises). The scheduler tick that hosts the pump stays independent of
  Loki being up — the constraint ADR-254 set — because the collector never
  blocks it: timeouts and circuit breakers belong to the telemetry clients.
- **Bounded by construction.** Lines read, samples kept, distinct counts,
  series and field lengths are capped by constants, so the prompt, the JSONB
  row and the Loki load stay small whatever the incident.
- **Allowlisted, never dumped.** A log line reaches the pack through a closed
  list of fields, each truncated and passed through the PII sanitizer: a
  register of what the model saw is the last place a user's message should
  land.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.core.constants import (
    DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS,
    DIAGNOSTICS_CONTEXT_HEAD_CHARS,
    DIAGNOSTICS_CONTEXT_LOG_LINES,
    DIAGNOSTICS_CONTEXT_LOG_SAMPLES,
    DIAGNOSTICS_CONTEXT_MAX_SERIES,
    DIAGNOSTICS_CONTEXT_TOP_COUNTS,
    DIAGNOSTICS_CONTEXT_WINDOW_MINUTES,
)
from src.core.process_info import uptime_seconds
from src.domains.diagnostics.evidence_recipes import EvidenceRecipe, LogRecipe, recipe_for
from src.domains.diagnostics.logql import build_log_query
from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE, render_query
from src.infrastructure.observability.metrics_diagnostics import (
    diagnostics_context_sources_total,
)
from src.infrastructure.observability.pii_filter import sanitize_string

if TYPE_CHECKING:
    from src.domains.diagnostics.models import Incident
    from src.infrastructure.telemetry.loki import LokiClient
    from src.infrastructure.telemetry.models import LokiLine
    from src.infrastructure.telemetry.prometheus import PrometheusClient

logger = structlog.get_logger(__name__)

#: Log fields allowed into the pack, in the order they are rendered. Closed on
#: purpose: `message`, `content`, `text`, `email`, `user_email` and every other
#: field a line may carry never travel, whatever they are named.
_ALLOWED_LOG_FIELDS: tuple[str, ...] = (
    "event",
    "level",
    "logger",
    "operation",
    "error",
    "last_error",
    "error_type",
    "reason",
    "attempt",
    "max_retries",
    "status_code",
    "run_id",
)

#: Fields whose head names the failure for the counts table, first one present.
_HEAD_FIELDS: tuple[str, ...] = ("error", "last_error", "reason")

#: Short commit prefix: enough to name a build, short enough for a prompt.
_COMMIT_CHARS = 12


def _clean(value: object, limit: int = DIAGNOSTICS_CONTEXT_FIELD_MAX_CHARS) -> str:
    """Bounded, sanitised text of any field value."""
    return sanitize_string(str(value))[:limit]


def _runtime_block(window_minutes: int) -> dict[str, object]:
    """Which build has been running for how long — "recent changes" answered."""
    return {
        "version": str(settings.app_version),
        "commit": str(settings.git_commit_sha or "")[:_COMMIT_CHARS],
        "build_date": str(getattr(settings, "build_date", "") or ""),
        "uptime_seconds": uptime_seconds(),
        "window_minutes": window_minutes,
    }


async def _collect_metric(
    prom_client: PrometheusClient, query_id: str, window_minutes: int
) -> dict[str, object]:
    """One catalogue query rendered and read; unavailable on any failure."""
    query = QUERY_CATALOGUE[query_id]
    block: dict[str, object] = {
        "query_id": query_id,
        "title": query.title,
        # The catalogue's unit travels with the values: "25" cannot be told
        # from 25 seconds, and the panel renders the same suffix the checks do.
        "unit": query.unit,
        "status": "unavailable",
        "error": None,
        "series": [],
        "truncated": False,
    }
    try:
        promql = render_query(query_id, window_minutes=window_minutes)
        result = await prom_client.instant_query(promql)
    except Exception as exc:  # noqa: BLE001 — a source failing is data, never an exception
        block["error"] = f"exception:{type(exc).__name__}"
        diagnostics_context_sources_total.labels(source="prometheus", status="unavailable").inc()
        return block
    if result.status != "ok":
        block["error"] = result.error
        diagnostics_context_sources_total.labels(source="prometheus", status="unavailable").inc()
        return block
    series = [
        {"labels": dict(sample.metric), "value": float(sample.value)}
        for sample in result.samples[:DIAGNOSTICS_CONTEXT_MAX_SERIES]
    ]
    block.update(
        status="ok",
        error=None,
        series=series,
        truncated=len(result.samples) > DIAGNOSTICS_CONTEXT_MAX_SERIES,
    )
    diagnostics_context_sources_total.labels(source="prometheus", status="ok").inc()
    return block


def _keep(line: LokiLine, recipe: LogRecipe) -> bool:
    """Recipe filter applied client-side: the builder offers one event at most."""
    if recipe.levels and line.level and line.level not in recipe.levels:
        return False
    if not recipe.events:
        return True
    payload = line.payload or {}
    return str(payload.get("event", "")) in recipe.events


def _sample_of(line: LokiLine) -> dict[str, object]:
    """One line through the allowlist, every value bounded and sanitised."""
    sample: dict[str, object] = {"ts": line.ts.isoformat(), "level": line.level}
    payload = line.payload
    if payload is None:
        sample["event"] = ""
        sample["error"] = _clean(line.raw)
        return sample
    for field in _ALLOWED_LOG_FIELDS:
        if field in payload and payload[field] is not None:
            sample[field] = _clean(payload[field])
    sample.setdefault("event", "")
    return sample


def _head_of(line: LokiLine) -> str:
    """The short text that names the failure in the counts table."""
    payload = line.payload
    if payload is None:
        return _clean(line.raw, DIAGNOSTICS_CONTEXT_HEAD_CHARS)
    for field in _HEAD_FIELDS:
        if payload.get(field):
            return _clean(payload[field], DIAGNOSTICS_CONTEXT_HEAD_CHARS)
    return ""


async def _collect_logs(
    loki_client: LokiClient, recipe: LogRecipe, window_minutes: int
) -> dict[str, object]:
    """The recipe's log lines: counted by (event, level, head), then sampled."""
    bounded = build_log_query(
        recipe.service, minutes=window_minutes, limit=DIAGNOSTICS_CONTEXT_LOG_LINES
    )
    try:
        result = await loki_client.query_range(
            bounded.logql, start=bounded.start, end=bounded.end, limit=bounded.limit
        )
    except Exception as exc:  # noqa: BLE001 — a source failing is data, never an exception
        diagnostics_context_sources_total.labels(source="loki", status="unavailable").inc()
        return {
            "status": "unavailable",
            "service": recipe.service.value,
            "error": f"exception:{type(exc).__name__}",
        }
    if result.status != "ok":
        diagnostics_context_sources_total.labels(source="loki", status="unavailable").inc()
        return {"status": "unavailable", "service": recipe.service.value, "error": result.error}

    kept = [line for line in result.lines if _keep(line, recipe)]
    counter: Counter[tuple[str, str, str]] = Counter()
    for line in kept:
        event = str((line.payload or {}).get("event", "")) if line.payload is not None else ""
        counter[(event, line.level, _head_of(line))] += 1
    ranked = counter.most_common()
    counts = [
        {"event": event, "level": level, "head": head, "count": count}
        for (event, level, head), count in ranked[:DIAGNOSTICS_CONTEXT_TOP_COUNTS]
    ]
    diagnostics_context_sources_total.labels(source="loki", status="ok").inc()
    return {
        "status": "ok",
        "service": recipe.service.value,
        "lines_read": len(result.lines),
        "lines_kept": len(kept),
        "counts": counts,
        "counts_truncated": len(ranked) > DIAGNOSTICS_CONTEXT_TOP_COUNTS,
        # Newest first, as Loki returned them.
        "samples": [_sample_of(line) for line in kept[:DIAGNOSTICS_CONTEXT_LOG_SAMPLES]],
    }


async def collect_diagnosis_context(
    incident: Incident,
    *,
    prom_client: PrometheusClient,
    loki_client: LokiClient,
) -> dict[str, object]:
    """The evidence pack for one incident, per its declared recipe.

    Never raises: each source degrades on its own and the runtime block is
    always present, so the pump can hand the model whatever was reachable.

    Args:
        incident: The incident being diagnosed (its correlation key selects
            the recipe).
        prom_client: Prometheus reader (never raises by contract).
        loki_client: Loki reader (never raises by contract).

    Returns:
        A JSON-serialisable mapping: ``recipe``, ``window_minutes``,
        ``runtime``, ``metrics`` (one block per query) and ``logs``.
    """
    recipe: EvidenceRecipe | None = recipe_for(incident.correlation_key)
    window = recipe.window_minutes if recipe is not None else DIAGNOSTICS_CONTEXT_WINDOW_MINUTES
    context: dict[str, object] = {
        "recipe": recipe.correlation_key if recipe is not None else None,
        "window_minutes": window,
        "runtime": _runtime_block(window),
        "metrics": [],
        "logs": {"status": "skipped"},
    }
    if recipe is None:
        return context
    try:
        context["metrics"] = [
            await _collect_metric(prom_client, query_id, window) for query_id in recipe.prom_queries
        ]
        if recipe.logs is not None:
            context["logs"] = await _collect_logs(loki_client, recipe.logs, window)
    except Exception as exc:  # noqa: BLE001 — the pack is best-effort, the diagnosis is not
        logger.warning(
            "diagnostics_context_collection_failed",
            correlation_key=incident.correlation_key,
            error=str(exc),
        )
    return context
