"""A favorite is a local UI state change requiring exact human confirmation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.relation_favorite_schemas import (
    RelationFavoritePatch,
    RelationFavoriteRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

RELATION_FAVORITE_OPERATION = ApplicationOperationSpec(
    operation_id="relation_favorite.update",
    tool_name="set_lia_relation_favorite_tool",
    sections=("relations",),
    input_model=RelationFavoritePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
RELATION_FAVORITE_MANIFEST = ToolManifest(
    name=RELATION_FAVORITE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to star or unstar the current account's displayed relationship card. Select its displayed name and explicit starred boolean. Source name folding and user-declared merges determine the identity. Unstarring removes every saved star belonging to that displayed identity, including merged-away spellings; other relationships, source records, messages and debriefs remain intact. An already established boolean is a verified no-op. The approved identity and its star records are compared under the same source owner lock used by UI favorites/merges/splits; a changed grouping requires a new proposal. No provider request, debrief generation, account sharing or message relay. Use get_lia_relations_tool to inspect the local cards. Never infer a merge or another account from a display name.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Displayed name and explicit favorite state",
            schema=RelationFavoriteRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Exact before/after favorite approval"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_relations",
    initiative_eligible=False,
    semantic_keywords=["favorite relationship", "star relationship", "unstar relationship"],
    display=DisplayMetadata(emoji="⭐", i18n_key="set_lia_relation_favorite", category="tool"),
)
