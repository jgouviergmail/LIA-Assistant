"""An observed companion summary is generated only after explicit paid consent."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.psyche_summary_schemas import (
    PsycheSummaryPatch,
    PsycheSummaryRequest,
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

PSYCHE_SUMMARY_OPERATION = ApplicationOperationSpec(
    operation_id="psyche.summary",
    tool_name="generate_lia_psyche_summary_tool",
    sections=("psyche",),
    input_model=PsycheSummaryPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PSYCHE,),
)

PSYCHE_SUMMARY_MANIFEST = ToolManifest(
    name="generate_lia_psyche_summary_tool",
    agent="setting_agent",
    description="Prepare mandatory human confirmation to generate the current account's companion psyche summary using the existing configured psyche_summary model. Read existing psyche facts first with get_lia_psyche_tool; that observational tool costs no summary call. Generation consumes accounted platform tokens under quotas and can initialize absent companion state after approval. Summary describes the companion, not a medical diagnosis of the user. Source prompt language and current personality/settings are retained. Changed source data, expired approval or withdrawn authority refuse generation or release of prose. Source provider failure may return its template fallback despite already incurred cost. Never automatically replay an uncertain or partial result. Return only observed output; no claim that summary text is stored as a narrative.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit paid current-account summary request",
            schema=PsycheSummaryRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending paid summary confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_psyche",
    initiative_eligible=False,
    semantic_keywords=["generate companion psyche summary", "summarize LIA mood"],
    display=DisplayMetadata(emoji="🧠", i18n_key="generate_lia_psyche_summary", category="tool"),
)
