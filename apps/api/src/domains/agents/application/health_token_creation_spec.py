"""A one-use originating-browser continuation returns the ingestion secret outside the model."""

from src.domains.agents.application.health_token_creation_schemas import (
    HealthTokenCreatePatch,
    HealthTokenCreateRequest,
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

HEALTH_TOKEN_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="health_token.create",
    tool_name="create_lia_health_ingestion_token_tool",
    sections=("health-metrics",),
    input_model=HealthTokenCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)

HEALTH_TOKEN_CREATE_MANIFEST = ToolManifest(
    name=HEALTH_TOKEN_CREATE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to create one owned health ingestion token with the existing optional source label. Requires an authenticated originating browser. Proposal and approval do not create any token. The approved browser explicitly continues once; the secret is returned only there, never to the model, drafts, registers, status, SSE or history. Existing measurements and tokens remain. Native/deployment/active-account/session authority and original expiry are checked at write and delivery. No model call. A lost response is observed through public metadata, never replayed to recover the secret; revoke the observed token before separately creating another if needed. Do not ask the user to paste its secret into chat.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Optional source token label",
            schema=HealthTokenCreateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending exact approval followed by browser-only secret delivery",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_health_metrics",
    initiative_eligible=False,
    semantic_keywords=["create health ingestion token", "connect watch health ingestion"],
    display=DisplayMetadata(
        emoji="💓", i18n_key="create_lia_health_ingestion_token", category="tool"
    ),
)
