"""
Catalogue manifests for Query (LocalQueryEngine) tools.
Optimized for orchestration efficiency.
"""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. LOCAL QUERY ENGINE
# ============================================================================
_query_desc = (
    "**Tool: local_query_engine_tool** - Analyze/filter in-memory data.\n"
    "**Operations**: filter, sort, group, aggregate (sum/avg/count), similarity.\n"
    "**Syntax**: Dot notation (e.g. 'payload.addresses.0.city').\n"
    "**Prerequisite**: Data MUST be fetched first via search/list tools."
)

local_query_engine_catalogue_manifest = ToolManifest(
    name="local_query_engine_tool",
    agent="query_agent",
    description=_query_desc,
    semantic_keywords=[
        "filter results",
        "sort results",
        "group by",
        "count",
        "aggregate",
        "analyze data",
        "filter contacts",
        "filter emails",
        "who has",
        "which ones have",
    ],
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=True,
            description="Query spec object: {operation, target_type, conditions, group_by, sort_by...}",
        ),
        ParameterSchema(
            name="source",
            type="string",
            required=False,
            description="Data source (def: 'registry')",
        ),
        ParameterSchema(
            name="output_as_registry",
            type="boolean",
            required=False,
            description="Update registry with results (def: True)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="summary_for_llm", type="string", description="Natural language summary"
        ),
        OutputFieldSchema(path="registry_updates", type="object", description="Result items map"),
        OutputFieldSchema(
            path="tool_metadata", type="object", description="Stats (total, returned)"
        ),
    ],
    cost=CostProfile(est_tokens_in=200, est_tokens_out=500, est_cost_usd=0.001, est_latency_ms=100),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="INTERNAL"
    ),
    context_key="querys",  # Must match CONTEXT_DOMAIN_QUERY (domain + "s" pattern)
    reference_examples=["summary_for_llm", "tool_metadata.total"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🧠", i18n_key="local_query_engine", visible=True, category="tool"
    ),
    initiative_eligible=False,  # Infrastructure tool, analyzes in-memory data not user sources
)

__all__ = ["local_query_engine_catalogue_manifest"]
