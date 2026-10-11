"""Explicit name-based grouping reuses the UI source transaction."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.relation_grouping_schemas import (
    RelationGroupingPatch,
    RelationGroupingRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

RELATION_GROUPING_OPERATION = ApplicationOperationSpec(
    operation_id="relation_grouping.update",
    tool_name="manage_lia_relation_grouping_tool",
    sections=("relations",),
    input_model=RelationGroupingPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

RELATION_GROUPING_MANIFEST = ToolManifest(
    name=RELATION_GROUPING_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation for the authenticated account's Relations-page name-based merge or split. Explicit action merge requires displayed source and target names; split takes the merged-away source spelling without target. Reuses source folding, canonical target resolution and alias path compression. When source is already an alias, merging reassigns that selected spelling and names pointing to it; it does not move every spelling of the previous group. Source data, contacts, phone calls, memories, stars and peer permissions remain stored; this is a local display grouping, never another account's identity or message destination. Affected stored relationship debriefs are invalidated as on the UI, including the previous group when reassigning a name. Builds already in flight may finish their paid work but their removed claim cannot publish a stale debrief. No new provider request, synthesis or quota spend. Never infer that two people are the same or propose a grouping absent an explicit user request. Private source snapshots pin the actual alias/invalidation scope; changed identity, debrief content or authority requires a fresh proposal. Read current cards with get_lia_relations_tool; a split is one recorded alias, not an unmerge of an entire group.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit merge/split and displayed source names",
            schema=RelationGroupingRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Exact identity change and stored-debrief invalidation approval",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_relations",
    initiative_eligible=False,
    semantic_keywords=[
        "merge relationship names",
        "split merged relationship",
        "undo relationship grouping",
    ],
    display=DisplayMetadata(emoji="🤝", i18n_key="manage_lia_relation_grouping", category="tool"),
)
