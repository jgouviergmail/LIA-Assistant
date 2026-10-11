"""Source debrief generation is always an explicitly confirmed action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildPatch,
    RelationDebriefBuildRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

RELATION_DEBRIEF_BUILD_OPERATION = ApplicationOperationSpec(
    operation_id="relation_debrief.build",
    tool_name="generate_lia_relation_debrief_tool",
    sections=("relations",),
    input_model=RelationDebriefBuildPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RELATION_DEBRIEF,),
)
RELATION_DEBRIEF_BUILD_MANIFEST = ToolManifest(
    name=RELATION_DEBRIEF_BUILD_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to build the current account's Relations-page debrief for an explicit displayed name. Optional force asks again even when today's exists; unchanged evidence can reuse the stored body without another model call. Uses source identity/grouping, saved overview scope, local day, configured relation_debrief model, daily per-account rate bucket, account/instance usage ceilings, source claim/fencing and recorded token/cost accounting. Preparation makes no claim, provider request or model call. Confirmation pins identity, preferences and current debrief; changes require a new proposal. No account or private comparison input. Fresh native/account/platform/personal/scope/expiry guards run before claim, external work, paid invocation and settlement; locks are released before provider/model work. Failed or busy builds are not successful generation; previous bodies can remain after failure. Paid work may finish after withdrawal but prose is suppressed, with acknowledged source effects reported separately. Stored reading is get_lia_relation_debrief_tool; never generate when the user asked only what is already stored.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Displayed name and explicit force boolean",
            schema=RelationDebriefBuildRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending paid build confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_relations",
    initiative_eligible=False,
    semantic_keywords=["generate relationship debrief", "rebuild relationship synthesis"],
    display=DisplayMetadata(emoji="🤝", i18n_key="generate_lia_relation_debrief", category="tool"),
)
