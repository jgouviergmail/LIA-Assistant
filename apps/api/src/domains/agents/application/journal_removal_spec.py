"""One explicitly scoped native command covers source individual and complete removal."""

from src.domains.agents.application.journal_removal_schemas import (
    JournalDeletePatch,
    JournalDeleteRequest,
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

JOURNAL_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="journal_entries.delete",
    tool_name="delete_lia_journal_entries_tool",
    sections=("journals",),
    input_model=JournalDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.JOURNALS,),
)

JOURNAL_DELETE_MANIFEST = ToolManifest(
    name="delete_lia_journal_entries_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to permanently remove one owned journal entry or ALL active/archived entries. request.entry_id is REQUIRED: an owned UUID selects one entry; explicit null selects every current-account entry. First read entries with get_lia_journals_tool. The source supplies complete counts, character size, attached evidence count and full public facts for an individual entry; display page limits never narrow bulk scope. Private full-row fingerprints stay out of approval/model context. Changes/new rows before confirmation require a new proposal. The source invalidates compiled portrait and cascades attached evidence; settings, conversations, memories and interests remain. Journal observations may be learned again. Stored records are removable when the personal journal switch is off; native/source operator authority must be enabled. No provider/model call, extraction, consolidation or immediate new portrait.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit owned entry UUID, or explicit null for complete removal",
            schema=JournalDeleteRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact complete removal confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_journals",
    initiative_eligible=False,
    semantic_keywords=[
        "delete journal entry",
        "delete all journals",
        "erase assistant observations",
    ],
    display=DisplayMetadata(emoji="📓", i18n_key="delete_lia_journal_entries", category="tool"),
)
