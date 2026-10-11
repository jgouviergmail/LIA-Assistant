"""The exact source chart contract is distinct from the existing health-agent summaries."""

from src.domains.agents.application.health_aggregate_schemas import (
    HEALTH_CHART_MAX_BUCKETS,
    HealthAggregateRead,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.health_metrics.schemas import HealthMetricAggregateResponse

HEALTH_AGGREGATE_OPERATION = ApplicationOperationSpec(
    operation_id="health_chart.read",
    tool_name="get_lia_health_chart_tool",
    sections=("health-metrics",),
    input_model=HealthAggregateRead,
    output_model=HealthMetricAggregateResponse,
    kind=OperationKind.READ,
)

HEALTH_AGGREGATE_MANIFEST = ToolManifest(
    name=HEALTH_AGGREGATE_OPERATION.tool_name,
    agent="setting_agent",
    description=f"Read the current account's exact Settings Health Metrics chart points and period-wide averages. Use hour/day/week/month/year with timezone-aware inclusive from_ts and exclusive to_ts; omitted bounds use the source UI defaults. Native/deployment/account authority and existing assistant-health consent are checked before and after SQL aggregation. Source UTC bucket alignment, empty gaps, kind registry, weighted HR averages and steps-per-day over the actual full window are preserved. No raw history is materialized in application memory. At most {HEALTH_CHART_MAX_BUCKETS} buckets: a larger request is refused before querying, so choose a coarser period or explicit narrower window; no points are silently dropped. Measurements remain mutable. No model, mutation or medical interpretation. Existing health_agent tools remain available for summaries and baseline comparisons.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description=f"Source chart period/window; at most {HEALTH_CHART_MAX_BUCKETS} complete UTC buckets",
            schema=HealthAggregateRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="points",
            type="array",
            description="Complete source-compatible chart buckets including gaps",
        ),
        OutputFieldSchema(
            path="averages", type="object", description="Full requested-window source averages"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_health_metrics",
    initiative_eligible=False,
    semantic_keywords=["health chart values", "health bucketed averages", "steps chart"],
    display=DisplayMetadata(emoji="💓", i18n_key="get_lia_health_chart", category="tool"),
)
