"""
Catalogue manifests for Context tools.
Optimized for orchestration efficiency.
"""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# Shared Constraints
# ============================================================================
_DOMAIN_PARAM = ParameterSchema(
    name="domain",
    type="string",
    required=True,
    description="Context domain (contacts, emails, events).",
    constraints=[ParameterConstraint(kind="min_length", value=1)],
)

# ============================================================================
# 1. RESOLVE REFERENCE
# ============================================================================
_resolve_desc = (
    "**Tool: resolve_reference** - Resolve contextual reference to item ID.\n"
    "**Use for**: 'first', '2nd one', 'last one', 'the previous one'.\n"
    "**Returns**: Resolved item with confidence score."
)

resolve_reference_catalogue_manifest = ToolManifest(
    name="resolve_reference",
    agent="context_agent",
    description=_resolve_desc,
    semantic_keywords=[
        # Ordinal references (base) - for resolving "the first one" to actual item
        "the first one",
        "the last one",
        "the second one",
        "that one",
        "this one",
        "the previous",
        # Numeric ordinals
        "the 1st",
        "the 2nd",
        "the 3rd",
        "number one",
        "number two",
        # NOTE: DO NOT add "details of the first" etc. here!
        # Those queries should match domain-specific tools (get_contact_details_tool, etc.)
        # The context resolution happens BEFORE semantic router via context_resolution_service
    ],
    parameters=[
        ParameterSchema(
            name="reference",
            type="string",
            required=True,
            description="Ref to resolve ('2', 'last', 'Name').",
        ),
        ParameterSchema(
            name="domain",
            type="string",
            required=False,
            description="Target domain. Optional if auto-detectable.",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Resolution success"),
        OutputFieldSchema(path="item", type="object", nullable=True, description="Resolved item"),
        OutputFieldSchema(
            path="confidence", type="number", nullable=True, description="Score 0.0-1.0"
        ),
        OutputFieldSchema(
            path="match_type", type="string", nullable=True, description="index/fuzzy/keyword"
        ),
        OutputFieldSchema(path="error", type="string", nullable=True, description="Error code"),
        OutputFieldSchema(path="candidates", type="array", description="Ambiguity candidates"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=100, est_cost_usd=0.0, est_latency_ms=50),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    max_iterations=1,
    supports_dry_run=False,
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🔗", i18n_key="resolve_reference", visible=True, category="context"
    ),
)

# ============================================================================
# 2. SET CURRENT ITEM
# ============================================================================
set_current_item_catalogue_manifest = ToolManifest(
    name="set_current_item",
    agent="context_agent",
    description="**Tool: set_current_item** - Mark item as 'current' for future references.",
    parameters=[
        ParameterSchema(
            name="reference", type="string", required=True, description="Item reference/ID."
        ),
        _DOMAIN_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success status"),
        OutputFieldSchema(path="message", type="string", description="Result message"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=50, est_cost_usd=0.0, est_latency_ms=30),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📌", i18n_key="set_current_item", visible=True, category="context"
    ),
)

# ============================================================================
# 3. GET CONTEXT STATE (Debug)
# ============================================================================
get_context_state_catalogue_manifest = ToolManifest(
    name="get_context_state",
    agent="context_agent",
    description="**Tool: get_context_state** - DEBUG: Get active context state.",
    parameters=[_DOMAIN_PARAM],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="state", type="object", description="Context object"),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=80, est_cost_usd=0.0, est_latency_ms=40),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📊", i18n_key="get_context_state", visible=False, category="context"
    ),
)

# ============================================================================
# 4. LIST ACTIVE DOMAINS (Debug)
# ============================================================================
list_active_domains_catalogue_manifest = ToolManifest(
    name="list_active_domains",
    agent="context_agent",
    description="**Tool: list_active_domains** - DEBUG: List domains with active context.",
    parameters=[],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="domains", type="array", description="List of domains"),
    ],
    cost=CostProfile(est_tokens_in=20, est_tokens_out=60, est_cost_usd=0.0, est_latency_ms=30),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📁", i18n_key="list_active_domains", visible=False, category="context"
    ),
)

# ============================================================================
# 5. GET CONTEXT LIST (Batch)
# ============================================================================
_list_desc = (
    "**Tool: get_context_list** - Get all items from active context (max 10).\n"
    "**Use for**: BATCH operations ('all these', 'all of them', 'all contacts').\n"
    "**Output**: Full array with metadata."
)

get_context_list_catalogue_manifest = ToolManifest(
    name="get_context_list",
    agent="context_agent",
    description=_list_desc,
    parameters=[_DOMAIN_PARAM],
    outputs=[
        OutputFieldSchema(path="success", type="boolean", description="Success"),
        OutputFieldSchema(path="items", type="array", description="Full items list"),
        OutputFieldSchema(path="total_count", type="integer", description="Count"),
        OutputFieldSchema(path="truncated", type="boolean", description="Is truncated"),
    ],
    cost=CostProfile(est_tokens_in=30, est_tokens_out=200, est_cost_usd=0.0, est_latency_ms=50),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    max_iterations=1,
    supports_dry_run=False,
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📝", i18n_key="get_context_list", visible=True, category="context"
    ),
)
