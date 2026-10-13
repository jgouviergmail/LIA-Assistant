"""An explicitly confirmed source maintenance request may incur platform-model costs."""

from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationPatch,
    JournalConsolidationRequest,
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
from src.domains.feature_switches.registry import PlatformCapability

JOURNAL_CONSOLIDATE_OPERATION = ApplicationOperationSpec(
    operation_id="journals.consolidate",
    tool_name="consolidate_lia_journals_tool",
    sections=("journals",),
    input_model=JournalConsolidationPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.JOURNALS,),
)

JOURNAL_CONSOLIDATE_MANIFEST = ToolManifest(
    name="consolidate_lia_journals_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to run the existing journal consolidation for the current account. Read source settings first. Personal journal learning and platform/native journal tools must remain enabled. Preview all-owned corpus counts (including archived entries for comparison), current configuration and history consent; maintenance reviews ACTIVE entries and current authorized portrait sources. The source model may edit, merge, create or remove journal entries and recompile the portrait. No model decisions are predicted, no journal prose/private source hashes are placed in the proposal, and no model/embedding call occurs before approval. Model and embedding calls consume accounted tokens/platform budget under per-call quotas; existing source timeout and account lease apply. Changed source/settings, expiry or withdrawn authority refuse old approval at paid/write boundaries. Outcomes may be busy, no-op, failed or uncertain despite spent tokens; never automatically replay an unknown completion or promise a new portrait before observing source results.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit current-account maintenance request",
            schema=JournalConsolidationRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending paid maintenance confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_journals",
    initiative_eligible=False,
    semantic_keywords=[
        "consolidate my journal",
        "recompile my journal portrait",
        "maintain journal entries",
    ],
    display=DisplayMetadata(emoji="📓", i18n_key="consolidate_lia_journals", category="tool"),
)
