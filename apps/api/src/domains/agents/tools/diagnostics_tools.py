"""Self-diagnostics chat tools (admin-only, read-only).

The "LIA, diagnose yourself" surface: four tools over the snapshot store, the
named-query catalogue, the bounded LogQL builder and the incident memory.
Doctrine (spec 2026-08-27, pillar 6):

- admin check AT CALL TIME via the shared gate (devops pattern) — non-admins
  get the same FORBIDDEN failure wording as the DevOps tool;
- query text never comes from the model: it picks a catalogue key or bounded
  builder parameters, and every enforced bound is published in the manifests;
- shown counts are exact, and a hit cap is stated (``truncated``), never
  applied in silence;
- telemetry never raises: an unavailable source is a structured failure.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.constants import DIAGNOSTICS_AGENT_NAME
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.admin_gate import user_is_superuser
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.diagnostics.logql import DiagService, build_log_query
from src.domains.diagnostics.query_catalogue import QUERY_CATALOGUE, render_query
from src.domains.diagnostics.repository import DiagnosticsRepository
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)
from src.infrastructure.telemetry.loki import LokiClient
from src.infrastructure.telemetry.prometheus import PrometheusClient

logger = structlog.get_logger(__name__)

__all__ = [
    "platform_health_tool",
    "platform_incidents_tool",
    "platform_logs_tool",
    "platform_metrics_tool",
]

#: Same wording as the DevOps tool — one consistent refusal for admin surfaces.
_FORBIDDEN_MESSAGE = "This feature is restricted to administrators."

#: Cap on samples/lines/incidents embedded in a tool payload (token budget);
#: the exact totals are always carried alongside.
_MAX_EMBEDDED_ROWS = 50


async def _admin_gate(
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None,
    tool_name: str,
) -> UnifiedToolOutput | str:
    """Validate the runtime and require superuser privileges.

    Args:
        runtime: Injected tool runtime.
        tool_name: Calling tool name (for logs).

    Returns:
        The user id (str) when allowed, or the failure output to return.
    """
    validated = validate_runtime_config(runtime, tool_name)
    if isinstance(validated, UnifiedToolOutput):
        return validated
    if not await user_is_superuser(validated.user_id):
        return UnifiedToolOutput.failure(message=_FORBIDDEN_MESSAGE, error_code="FORBIDDEN")
    return str(validated.user_id)


@registered_tool
@track_tool_metrics(
    tool_name="platform_health",
    agent_name=DIAGNOSTICS_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().diagnostics_rate_limit_calls,
    window_seconds=lambda: get_settings().diagnostics_rate_limit_window,
    scope="user",
)
async def platform_health_tool(
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Current platform health: latest self-check snapshot, firing alerts, open incidents.

    Admin-only. Read-only. Sources that are unreachable are reported as
    'unavailable' — this tool works even while the observability tier is down.

    Args:
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with overall verdict, per-check results, active
        alerts and the exact open-incident count.
    """
    gate = await _admin_gate(runtime, "platform_health_tool")
    if isinstance(gate, UnifiedToolOutput):
        return gate

    # One overview implementation for both surfaces (service.build_overview —
    # the admin REST endpoint serves the exact same composition).
    from src.domains.diagnostics.service import build_overview

    async with get_db_context() as db:
        data = await build_overview(db)
    message = (
        f"Platform health: {data.get('overall', 'no snapshot yet')} | "
        f"{data.get('total_active_alerts', 0)} firing alert(s) | "
        f"{data.get('open_incidents', 0)} open incident(s)"
    )
    return UnifiedToolOutput.action_success(message=message, structured_data=data)


@registered_tool
@track_tool_metrics(
    tool_name="platform_metrics",
    agent_name=DIAGNOSTICS_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().diagnostics_rate_limit_calls,
    window_seconds=lambda: get_settings().diagnostics_rate_limit_window,
    scope="user",
)
async def platform_metrics_tool(
    query_key: Annotated[
        str,
        "Named query key from the curated catalogue (e.g. api_error_rate, "
        "llm_failure_rate, disk_usage_percent). Free-form PromQL is not accepted.",
    ],
    window_minutes: Annotated[int, "Time window in minutes (clamped to 1-1440)"] = 15,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Run one curated platform metric query (bounded parameters, exact values).

    Admin-only. The catalogue is the only PromQL producer: an unknown key is
    an INVALID_INPUT listing the available keys (and counts toward the
    free-form-query escalation signal).

    Args:
        query_key: Catalogue key.
        window_minutes: Rate/increase window; out-of-bounds values are clamped.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with the samples and their unit.
    """
    gate = await _admin_gate(runtime, "platform_metrics_tool")
    if isinstance(gate, UnifiedToolOutput):
        return gate

    from src.infrastructure.observability.metrics_diagnostics import (
        diagnostics_catalogue_miss_total,
    )

    if query_key not in QUERY_CATALOGUE:
        diagnostics_catalogue_miss_total.labels(surface="chat_tool").inc()
        available = ", ".join(sorted(QUERY_CATALOGUE))
        return UnifiedToolOutput.failure(
            message=f"Unknown query '{query_key}'. Available queries: {available}",
            error_code="INVALID_INPUT",
            metadata={"available_keys": sorted(QUERY_CATALOGUE)},
        )

    settings = get_settings()
    query = QUERY_CATALOGUE[query_key]
    promql = render_query(query_key, window_minutes=float(window_minutes))
    result = await PrometheusClient(
        base_url=settings.diagnostics_prometheus_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    ).instant_query(promql)
    if result.status != "ok":
        return UnifiedToolOutput.failure(
            message=f"Prometheus is unavailable ({result.error}).",
            error_code="UNAVAILABLE",
            metadata={"source": "prometheus", "reason": result.error},
        )

    samples = [
        {"labels": sample.metric, "value": sample.value}
        for sample in result.samples[:_MAX_EMBEDDED_ROWS]
    ]
    data = {
        "query_key": query_key,
        "title": query.title,
        "unit": query.unit,
        "window_minutes": window_minutes,
        "samples": samples,
        "total_samples": len(result.samples),
        "truncated": len(result.samples) > _MAX_EMBEDDED_ROWS,
    }
    message = f"{query.title}: {len(result.samples)} sample(s), unit={query.unit}"
    return UnifiedToolOutput.action_success(message=message, structured_data=data)


@registered_tool
@track_tool_metrics(
    tool_name="platform_logs",
    agent_name=DIAGNOSTICS_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().diagnostics_rate_limit_calls,
    window_seconds=lambda: get_settings().diagnostics_rate_limit_window,
    scope="user",
)
async def platform_logs_tool(
    service: Annotated[
        str,
        "Compose service whose logs to read: api, web, postgres, redis, prometheus, "
        "loki, promtail, grafana, alertmanager, tempo, postgres-backup.",
    ],
    level: Annotated[str, "Level filter: debug/info/warning/error/critical. Empty = all."] = "",
    event: Annotated[str, "Exact structlog event name filter (snake_case). Empty = all."] = "",
    minutes: Annotated[int, "Look-back window in minutes (clamped to at most 24h)"] = 60,
    limit: Annotated[int, "Max lines (clamped to at most 500)"] = 0,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Read bounded platform logs from Loki (admin-only, injection-closed).

    Args:
        service: Target compose service (closed set).
        level: Optional level filter (closed set).
        event: Optional structlog event name (strict pattern).
        minutes: Look-back window; clamped to the hard cap.
        limit: Line budget; 0 uses the configured default; clamped to the cap.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with compact log entries and exact counts.
    """
    gate = await _admin_gate(runtime, "platform_logs_tool")
    if isinstance(gate, UnifiedToolOutput):
        return gate

    settings = get_settings()
    try:
        service_enum = DiagService(service)
        bounded = build_log_query(
            service=service_enum,
            level=level,
            event=event,
            minutes=minutes,
            limit=limit if limit > 0 else settings.diagnostics_loki_default_lines,
        )
    except ValueError as exc:
        return UnifiedToolOutput.failure(
            message=f"Invalid log query: {exc}",
            error_code="INVALID_INPUT",
            metadata={"services": [s.value for s in DiagService]},
        )

    result = await LokiClient(
        base_url=settings.diagnostics_loki_url,
        timeout_seconds=settings.diagnostics_http_timeout_seconds,
    ).query_range(bounded.logql, start=bounded.start, end=bounded.end, limit=bounded.limit)
    if result.status != "ok":
        return UnifiedToolOutput.failure(
            message=f"Loki is unavailable ({result.error}).",
            error_code="UNAVAILABLE",
            metadata={"source": "loki", "reason": result.error},
        )

    entries = [
        {
            "ts": line.ts.isoformat(),
            "container": line.container,
            "level": line.level,
            "event": str((line.payload or {}).get("event", "")),
            "logger": str((line.payload or {}).get("logger", "")),
        }
        for line in result.lines
    ]
    data = {
        "logql": bounded.logql,
        "count": len(entries),
        "limit": bounded.limit,
        # A page filled to its cap almost certainly dropped older lines;
        # stating it beats silently narrowing the window.
        "truncated": len(entries) >= bounded.limit,
        "lines": entries,
    }
    message = f"{len(entries)} log line(s) from '{service}' (limit {bounded.limit})"
    return UnifiedToolOutput.action_success(message=message, structured_data=data)


@registered_tool
@track_tool_metrics(
    tool_name="platform_incidents",
    agent_name=DIAGNOSTICS_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().diagnostics_rate_limit_calls,
    window_seconds=lambda: get_settings().diagnostics_rate_limit_window,
    scope="user",
)
async def platform_incidents_tool(
    incident_id: Annotated[str, "Incident UUID for the detail view. Empty = list open."] = "",
    include_resolved: Annotated[bool, "List resolved incidents too"] = False,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """List platform incidents, or show one incident with its stored diagnosis.

    Admin-only. Totals are exact (COUNT(*) over the filtered set).

    Args:
        incident_id: Incident UUID; empty lists instead.
        include_resolved: When listing, include resolved incidents.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with the incident list (exact total) or the detail.
    """
    gate = await _admin_gate(runtime, "platform_incidents_tool")
    if isinstance(gate, UnifiedToolOutput):
        return gate

    async with get_db_context() as db:
        repo = DiagnosticsRepository(db)
        if incident_id:
            try:
                parsed = UUID(incident_id)
            except ValueError:
                return UnifiedToolOutput.failure(
                    message=f"'{incident_id}' is not a valid incident id.",
                    error_code="INVALID_INPUT",
                )
            incident = await repo.get_incident(parsed)
            if incident is None:
                return UnifiedToolOutput.failure(
                    message=f"No incident with id {incident_id}.",
                    error_code="NOT_FOUND",
                )
            detail = {
                "id": str(incident.id),
                "correlation_key": incident.correlation_key,
                "source": incident.source,
                "severity": incident.severity,
                "status": incident.status,
                "title": incident.title,
                "opened_at": incident.opened_at.isoformat(),
                "last_seen_at": incident.last_seen_at.isoformat(),
                "evidence": incident.evidence,
                "diagnosis": incident.diagnosis,
                "action_log": incident.action_log,
            }
            return UnifiedToolOutput.action_success(
                message=f"Incident {incident.correlation_key} ({incident.status})",
                structured_data=detail,
            )

        status = None if include_resolved else "open"
        rows, total = await repo.list_incidents(status=status, page=1, page_size=_MAX_EMBEDDED_ROWS)

    incidents = [
        {
            "id": str(row.id),
            "correlation_key": row.correlation_key,
            "severity": row.severity,
            "status": row.status,
            "title": row.title,
            "opened_at": row.opened_at.isoformat(),
            "has_diagnosis": row.diagnosis is not None,
        }
        for row in rows
    ]
    data = {
        "total": total,
        "shown": len(incidents),
        "truncated": total > len(incidents),
        "incidents": incidents,
    }
    return UnifiedToolOutput.action_success(
        message=f"{total} incident(s), showing {len(incidents)}",
        structured_data=data,
    )
