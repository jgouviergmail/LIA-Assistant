"""Manual editing publishes the effective source transition, never invented proof."""

from src.domains.agents.application.journal_update_schemas import (
    JournalUpdatePatch,
    JournalUpdateRequest,
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

JOURNAL_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="journal_entries.update",
    tool_name="update_lia_journal_entry_tool",
    sections=("journals",),
    input_model=JournalUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.JOURNALS,),
)

JOURNAL_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_journal_entry_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation for sparse edits to one owned journal entry. Read source entries first. Source fields: title/content/mood/search_hints/confidence/level; null and empty patches are refused, [] clears hints. Source evidence rules determine the actual preview: changed content/level starts a new rule revision and resets current evidence/contradiction counts; requested high confidence can be clamped, retained contradictions can force low confidence. Title/hint edits preserve evidence. No reaction events or evidence are invented. Private semantic snapshots/evidence facts refuse concurrent changes; exposure counters alone do not invalidate approval. Embeddings run only after confirmation for changed title/content/hints, outside locks, under fresh quota/account authority. Verified effective no-ops spend nothing. Portrait invalidation follows the source policy without regeneration. Actual stored public values replace predictions in the receipt.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Owned entry UUID and explicit sparse source changes",
            schema=JournalUpdateRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending source-derived before/after confirmation",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_journals",
    initiative_eligible=False,
    semantic_keywords=[
        "edit journal entry",
        "correct journal observations",
        "change journal confidence",
    ],
    display=DisplayMetadata(emoji="📓", i18n_key="update_lia_journal_entry", category="tool"),
)
