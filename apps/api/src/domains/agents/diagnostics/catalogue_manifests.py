"""Catalogue manifests for the self-diagnostics tools (spec 2026-08-27).

Every bound the builders ENFORCE is PUBLISHED here (ADR-184 doctrine): the
window/limit clamps and the closed service/level sets appear as constraints so
the planner can produce valid calls instead of discovering the bounds by
rejection. Mirrors the devops module layout.
"""

from src.core.constants import (
    DIAGNOSTICS_LOKI_MAX_LINES,
    DIAGNOSTICS_LOKI_MAX_RANGE_HOURS,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.diagnostics.logql import ALLOWED_LEVELS, DiagService

_PERMISSIONS = PermissionProfile(
    required_scopes=[],
    allowed_roles=[],  # Admin check at call time (shared gate) + DIAGNOSTICS_ENABLED flag
    hitl_required=False,  # Read-only tools: nothing to confirm
    data_classification="RESTRICTED",
)

_DISPLAY = DisplayMetadata(
    emoji="🩺",
    i18n_key="platform_diagnostics",
    visible=True,
    category="tool",
)


def _cost(latency_ms: int) -> CostProfile:
    """Uniform cost profile: local HTTP reads, no paid API."""
    return CostProfile(
        est_tokens_in=200,
        est_tokens_out=800,
        est_cost_usd=0.0,
        est_latency_ms=latency_ms,
    )


platform_health_catalogue_manifest = ToolManifest(
    name="platform_health_tool",
    agent="diagnostics_agent",
    description=(
        "**Tool: platform_health_tool** - Current platform health (administrators only).\n"
        "Returns the latest self-check snapshot (per-check verdicts with exact values), "
        "currently firing alerts, and the exact count of open incidents.\n"
        "**Use for**: 'diagnose yourself', 'is everything healthy', platform status questions."
    ),
    parameters=[],
    outputs=[
        OutputFieldSchema(path="overall", type="string", description="ok/degraded/critical"),
        OutputFieldSchema(path="checks", type="array", description="Per-check results"),
        OutputFieldSchema(path="active_alerts", type="array", description="Firing alerts"),
        OutputFieldSchema(
            path="open_incidents", type="integer", description="Exact open-incident count"
        ),
    ],
    cost=_cost(1500),
    permissions=_PERMISSIONS,
    semantic_keywords=[
        "platform health status diagnose yourself",
        "system status check everything healthy",
        "self diagnostics overall verdict alerts",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    display=_DISPLAY,
    initiative_eligible=False,
)

platform_metrics_catalogue_manifest = ToolManifest(
    name="platform_metrics_tool",
    agent="diagnostics_agent",
    description=(
        "**Tool: platform_metrics_tool** - Run ONE curated platform metric query "
        "(administrators only).\n"
        "Free-form PromQL is not accepted: pick a query_key from the curated catalogue "
        "(api_error_rate, api_latency_p95, http_request_rate, llm_failure_rate, "
        "llm_errors_by_kind, background_job_errors, dependency_up, disk_usage_percent, "
        "memory_usage_percent, circuit_breakers_open)."
    ),
    parameters=[
        ParameterSchema(
            name="query_key",
            type="string",
            required=True,
            description="Curated catalogue key (see tool description for the full list).",
        ),
        ParameterSchema(
            name="window_minutes",
            type="integer",
            required=False,
            description="Rate/increase window in minutes. Out-of-bounds values are clamped.",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=1440),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="samples", type="array", description="Label sets + exact values"),
        OutputFieldSchema(path="unit", type="string", description="Value unit"),
        OutputFieldSchema(path="total_samples", type="integer", description="Exact sample count"),
    ],
    cost=_cost(800),
    permissions=_PERMISSIONS,
    semantic_keywords=[
        "platform metric error rate latency",
        "llm failure rate disk memory usage",
        "prometheus metric query platform",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    display=_DISPLAY,
    initiative_eligible=False,
)

platform_logs_catalogue_manifest = ToolManifest(
    name="platform_logs_tool",
    agent="diagnostics_agent",
    description=(
        "**Tool: platform_logs_tool** - Read bounded platform logs from Loki "
        "(administrators only).\n"
        "Filters: service (closed set), level, exact structlog event name. "
        "Range and line count are clamped to hard caps."
    ),
    parameters=[
        ParameterSchema(
            name="service",
            type="string",
            required=True,
            description="Compose service whose logs to read.",
            constraints=[
                ParameterConstraint(kind="enum", value=[s.value for s in DiagService]),
            ],
        ),
        ParameterSchema(
            name="level",
            type="string",
            required=False,
            description="Level filter; empty = all levels.",
            constraints=[
                ParameterConstraint(kind="enum", value=sorted(ALLOWED_LEVELS)),
            ],
        ),
        ParameterSchema(
            name="event",
            type="string",
            required=False,
            description="Exact structlog event name (snake_case); empty = all events.",
            constraints=[
                ParameterConstraint(kind="pattern", value=r"^[a-z0-9_.]{1,64}$"),
            ],
        ),
        ParameterSchema(
            name="minutes",
            type="integer",
            required=False,
            description="Look-back window in minutes.",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=DIAGNOSTICS_LOKI_MAX_RANGE_HOURS * 60),
            ],
        ),
        ParameterSchema(
            name="limit",
            type="integer",
            required=False,
            description="Max lines returned (0 = configured default).",
            constraints=[
                ParameterConstraint(kind="minimum", value=0),
                ParameterConstraint(kind="maximum", value=DIAGNOSTICS_LOKI_MAX_LINES),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="lines", type="array", description="Compact log entries"),
        OutputFieldSchema(path="count", type="integer", description="Exact returned count"),
        OutputFieldSchema(
            path="truncated", type="boolean", description="True when the cap was hit"
        ),
    ],
    cost=_cost(1200),
    permissions=_PERMISSIONS,
    semantic_keywords=[
        "platform logs errors api service",
        "loki log search event level",
        "recent error logs diagnose",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    display=_DISPLAY,
    initiative_eligible=False,
)

platform_incidents_catalogue_manifest = ToolManifest(
    name="platform_incidents_tool",
    agent="diagnostics_agent",
    description=(
        "**Tool: platform_incidents_tool** - List platform incidents or show one with its "
        "stored diagnosis (administrators only). Totals are exact."
    ),
    parameters=[
        ParameterSchema(
            name="incident_id",
            type="string",
            required=False,
            description="Incident UUID for the detail view; empty lists incidents instead.",
        ),
        ParameterSchema(
            name="include_resolved",
            type="boolean",
            required=False,
            description="When listing, include resolved incidents too.",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="incidents", type="array", description="Incident summaries"),
        OutputFieldSchema(path="total", type="integer", description="Exact total count"),
        OutputFieldSchema(
            path="diagnosis", type="object", description="Stored diagnosis (detail view)"
        ),
    ],
    cost=_cost(600),
    permissions=_PERMISSIONS,
    semantic_keywords=[
        "platform incidents open resolved",
        "incident diagnosis root cause",
        "what went wrong outage history",
    ],
    tool_category="readonly",
    version="1.0.0",
    maintainer="Team AI",
    display=_DISPLAY,
    initiative_eligible=False,
)

DIAGNOSTICS_TOOL_MANIFESTS = (
    platform_health_catalogue_manifest,
    platform_metrics_catalogue_manifest,
    platform_logs_catalogue_manifest,
    platform_incidents_catalogue_manifest,
)
