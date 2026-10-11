"""Complete owned sample erasure has mandatory exact human approval."""

from src.domains.agents.application.health_removal_schemas import (
    HealthRemovalPatch,
    HealthRemovalRequest,
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

HEALTH_REMOVAL_OPERATION = ApplicationOperationSpec(
    operation_id="health_samples.delete",
    tool_name="delete_lia_health_samples_tool",
    sections=("health-metrics",),
    input_model=HealthRemovalPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

HEALTH_REMOVAL_MANIFEST = ToolManifest(
    name=HEALTH_REMOVAL_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to permanently remove every health sample of the explicit kind, or EVERY owned kind when kind is explicitly null, using the Settings source deletion. Preview complete owned counts by kind, not a displayed page. Raw values and private comparison hashes never enter approval/editor text; no sample is removed before consent. Data consent may be disabled: deletion of owned data is a management action, not permission to read values. Deployment/native/active-account authority and original approval deadline must remain valid. Changed samples or new rows refuse old approval. Source owner-first locking serializes ingestion; remaining selected rows and exact affected count are verified before commit. Ingestion tokens remain usable and may create new samples after erasure, unless separately revoked. Lost SQL acknowledgement is unknown even if erasure committed: never automatically replay. Derived baseline/chart queries reflect remaining raw data; learned memories/journals are separate records and are not erased by this action. No model call.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit source kind or explicit null for all owned samples",
            schema=HealthRemovalRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending irreversible erasure confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_health_metrics",
    initiative_eligible=False,
    semantic_keywords=["delete health measurements", "erase all health samples"],
    display=DisplayMetadata(emoji="💓", i18n_key="delete_lia_health_samples", category="tool"),
)
