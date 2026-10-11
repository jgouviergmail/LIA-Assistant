"""Owned ingestion-token revocation is an explicitly confirmed source management action."""

from src.domains.agents.application.health_token_schemas import (
    HealthTokenRevokePatch,
    HealthTokenRevokeRequest,
)
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

HEALTH_TOKEN_REVOKE_OPERATION = ApplicationOperationSpec(
    operation_id="health_token.revoke",
    tool_name="revoke_lia_health_ingestion_token_tool",
    sections=("health-metrics",),
    input_model=HealthTokenRevokePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HEALTH_TOKEN_REVOKE_MANIFEST = ToolManifest(
    name=HEALTH_TOKEN_REVOKE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to revoke one owned health ingestion token identified by the source metadata UUID. Read get_lia_health_ingestion_tokens_tool first. Display its public prefix, label and dates; no raw token/hash ever enters approval/editor text. Native/deployment/active-account authority and approval expiry are rechecked at source write/commit boundaries. Changed identity/label/revocation status refuses old approval; incidental last-use dates do not retarget the token. An already revoked token is an observed no-op. Owner-first locking serializes source ingestion, and pre-authenticated ingestion rechecks current token validity before writing. Revocation prevents future ingestion with that token, preserves already recorded health measurements and is irreversible; a new token is a separate secure request. No model call. Unknown completion is not replayable automatically.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Owned source ingestion-token UUID",
            schema=HealthTokenRevokeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact token revocation approval"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_health_metrics",
    initiative_eligible=False,
    semantic_keywords=["revoke health ingestion token", "disable watch ingestion token"],
    display=DisplayMetadata(
        emoji="💓", i18n_key="revoke_lia_health_ingestion_token", category="tool"
    ),
)
