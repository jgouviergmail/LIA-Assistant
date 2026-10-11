"""Reviewed manual creation follows the source public API, not automatic extraction limits."""

from src.domains.agents.application.journal_create_schemas import (
    JournalCreateConfiguration,
    JournalCreatePatch,
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

JOURNAL_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="journal_entries.create",
    tool_name="create_lia_journal_entry_tool",
    sections=("journals",),
    input_model=JournalCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.JOURNALS,),
)

JOURNAL_CREATE_MANIFEST = ToolManifest(
    name="create_lia_journal_entry_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to create one manual journal entry for the current account. The source public API defines theme, title, full content, mood and optional bounded search hints; it is LIA's journal, not a separate personal diary. Server-generated identity and all configuration are confirmed. Embeddings run only after approval, outside owner locks, with fresh authority and quota checks before each source call and accounted platform spend. Source provider failure can leave an entry without semantic vectors, as in the UI. The entry is active/manual, starts with source evidence/confidence defaults and invalidates the portrait without regenerating it. Character budgets configure future consolidation, not silently truncated manual content. No conversations, evidence events, consolidation or portrait generation are created.",
    parameters=[
        ParameterSchema(
            name="configuration",
            type="object",
            required=True,
            description="Complete manual source entry configuration",
            schema=JournalCreateConfiguration.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending full entry approval")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="create",
    binding_unit="lia_journals",
    initiative_eligible=False,
    semantic_keywords=["create manual journal entry", "add assistant journal note"],
    display=DisplayMetadata(emoji="📓", i18n_key="create_lia_journal_entry", category="tool"),
)
