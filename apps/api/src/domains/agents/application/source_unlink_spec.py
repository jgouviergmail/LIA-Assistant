"""Mandatory confirmed removal of one owned source, retaining its indexed documents."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkPatch,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

SOURCE_UNLINK_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_source.unlink",
    tool_name="unlink_lia_knowledge_source_tool",
    sections=("rag-spaces",),
    input_model=SourceUnlinkPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)

SOURCE_UNLINK_MANIFEST = ToolManifest(
    name=SOURCE_UNLINK_OPERATION.tool_name,
    agent="setting_agent",
    description=(
        "Prepare mandatory human confirmation to unlink one real owned knowledge-space Drive folder or Gmail label source. "
        "Use get_lia_knowledge_spaces_tool drive_sources/mail_sources for space_id, source_id and kind. "
        "This removes the source association and RETAINS all document rows, indexed chunks and stored files. "
        "No content deletion, provider call, sync or reindex is requested. Names are literal data. "
        "Inactive owned spaces and existing sources whose sync feature is disabled can be unlinked; system/foreign sources unavailable. "
        "A running sync, expired approval, changed parent/source/document identities, revoked account or disabled native/RAG capability refuses execution. "
        "Unknown commit never replays automatically. This tool cannot fulfill a request to delete the source's documents."
    ),
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned source identity; documents are always retained",
            schema=SourceUnlinkInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_knowledge_spaces",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "unlink a knowledge source",
        "remove Drive folder from my space",
        "unlink Gmail label and keep documents",
    ],
    display=DisplayMetadata(emoji="🔗", i18n_key="unlink_lia_knowledge_source", category="tool"),
)
