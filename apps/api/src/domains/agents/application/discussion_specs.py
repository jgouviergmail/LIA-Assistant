"""One finite declaration feeds both orchestration modes and native HITL execution."""

from src.domains.agents.application.discussion_schemas import (
    DiscussionDetailsRequest,
    DiscussionPageRequest,
    DiscussionPreferencesIntent,
    DiscussionPurgeIntent,
    DiscussionRebuildIntent,
    DiscussionUseIntent,
)
from src.domains.agents.application.operation_spec import (
    ApplicationEmptyRead,
    ApplicationOperationSpec,
    OperationKind,
)
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.proactive_discussions.api_schemas import DiscussionSettingsResponse
from src.domains.proactive_discussions.context_store.schemas import ContextGeneration
from src.domains.proactive_discussions.openings import OpeningPage, OpeningPageRequest, OpeningView

DISCUSSION_OPERATIONS = tuple(
    ApplicationOperationSpec(
        operation_id=operation,
        tool_name=tool,
        sections=("proactive-discussions",),
        input_model=model,
        output_model=output,
        kind=kind,
    )
    for operation, tool, model, output, kind in (
        (
            "discussions.list",
            "list_lia_discussions_tool",
            OpeningPageRequest,
            OpeningPage,
            OperationKind.READ,
        ),
        (
            "discussions.details",
            "get_lia_discussion_details_tool",
            DiscussionDetailsRequest,
            OpeningView,
            OperationKind.READ,
        ),
        (
            "proactive_discussions.read",
            "get_lia_proactive_discussions_tool",
            ApplicationEmptyRead,
            DiscussionSettingsResponse,
            OperationKind.READ,
        ),
        (
            "discussion_context.read",
            "get_lia_discussion_context_tool",
            DiscussionPageRequest,
            ContextGeneration,
            OperationKind.READ,
        ),
        (
            "proactive_discussions.update",
            "update_lia_proactive_discussions_tool",
            DiscussionPreferencesIntent,
            ApplicationExecutionOutcome,
            OperationKind.ACTION,
        ),
        (
            "discussion_context.use",
            "set_lia_discussion_context_use_tool",
            DiscussionUseIntent,
            ApplicationExecutionOutcome,
            OperationKind.ACTION,
        ),
        (
            "discussion_context.purge",
            "purge_lia_discussion_context_tool",
            DiscussionPurgeIntent,
            ApplicationExecutionOutcome,
            OperationKind.ACTION,
        ),
        (
            "discussion_context.rebuild",
            "rebuild_lia_discussion_context_tool",
            DiscussionRebuildIntent,
            ApplicationExecutionOutcome,
            OperationKind.ACTION,
        ),
    )
)
DISCUSSION_SPECS = {spec.operation_id: spec for spec in DISCUSSION_OPERATIONS}
_DESCRIPTIONS = {
    "discussions.list": "Read the owner's real archived personal discussion openings, exact filtered total and stable pagination. No provider access or new initiative. Distinct from event notifications.",
    "discussions.details": "Read one owned visible personal opening and its persisted explicit feedback. Never expose internal reasoning or reconstruct a deleted message.",
    "proactive_discussions.read": "Read personal proactive-discussion opt-in, activity hours, daily limit (null means unlimited), all independent sources/topics, pause and current producer/budget availability. These personal conversations are separate from proactive event notifications.",
    "discussion_context.read": "Read one private page of derived observations, episodes, qualified patterns and reversible non-usable exclusions, with native proofs, retention and rebuild state. The portrait is one independently controlled whole source. Reading starts no model or background job.",
    "proactive_discussions.update": "Prepare mandatory exact human approval to change optional personal discussion settings. Sparse changes preserve other fields and existing event notifications. New sources remain opt-in. No model call is started by a settings change.",
    "discussion_context.use": "Prepare exact approval to mark one owned derived item non-usable or restore its use. Exclusion acts before retrieval, pattern aggregation and models, survives purge/rebuild and covers supported descendants. Restoring a purged marker does not recreate erased content.",
    "discussion_context.purge": "Prepare exact approval to purge the whole derived discussion base or selected owned item UUIDs, with current scope/generation. Sources, memories and non-usable choices are preserved. Old workers cannot republish purged data; unchanged historical content stays forgotten until an explicit rebuild.",
    "discussion_context.rebuild": "Prepare exact approval to request a bounded reconstruction from currently permitted personal sources. Non-usable exclusions survive. After confirmation, a context-only task is triggered in the background without waiting for the periodic producer or discussion activity hours. Consent, fresh permissions, financial limits and concurrency fences still apply. It never sends a proactive message or guarantees successful completion.",
}
DISCUSSION_MANIFESTS = tuple(
    ToolManifest(
        name=spec.tool_name,
        agent="setting_agent",
        description=_DESCRIPTIONS[spec.operation_id],
        parameters=(
            []
            if spec.operation_id == "proactive_discussions.read"
            else [
                ParameterSchema(
                    name="request",
                    type="object",
                    required=True,
                    description="Closed selection or explicit requested changes, never identity or approval.",
                    schema=spec.input_model.model_json_schema(),
                )
            ]
        ),
        outputs=[
            OutputFieldSchema(
                path="data" if spec.kind == OperationKind.READ else "draft",
                type="object",
                description=(
                    "Private native projection"
                    if spec.kind == OperationKind.READ
                    else "Exact pending human confirmation"
                ),
            )
        ],
        cost=CostProfile(),
        permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
        mutation_policy="read" if spec.kind == OperationKind.READ else "draft",
        tool_category="readonly" if spec.kind == OperationKind.READ else "update",
        binding_unit="lia_proactive_discussions",
        initiative_eligible=False,
        semantic_keywords=[
            "proactive personal discussions",
            "discussion context",
            "non-usable personal context",
        ],
        display=DisplayMetadata(
            emoji="💬", i18n_key=spec.tool_name.removesuffix("_tool"), category="tool"
        ),
    )
    for spec in DISCUSSION_OPERATIONS
)
