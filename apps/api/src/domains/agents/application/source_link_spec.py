"""A standing source instruction always needs the native exact human approval."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.source_link_schemas import SourceLinkInput, SourceLinkPatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

SOURCE_LINK_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_source.link",
    tool_name="link_lia_knowledge_source_tool",
    sections=("rag-spaces",),
    input_model=SourceLinkPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)

SOURCE_LINK_MANIFEST = ToolManifest(
    name=SOURCE_LINK_OPERATION.tool_name,
    agent="setting_agent",
    description=(
        "Prepare mandatory human approval to link one real Google Drive folder or Gmail user label to an owned personal knowledge space. "
        "Get real space ids from get_lia_knowledge_spaces_tool and provider ids from get_lia_knowledge_source_options_tool; names are re-read from the provider. "
        "This creates a standing automatic synchronization instruction, which can later consume provider quotas and embedding costs through the existing Source jobs. "
        "Linking does not mean documents have already been imported or indexed. No immediate synchronization or embedding is performed by this action. "
        "Preparation and fresh execution read provider metadata (API quota, no LLM). Existing duplicate, same-kind quota and Drive tree-overlap rules remain enforced. "
        "Owned inactive spaces are supported. Foreign/system destinations, missing credentials, expired approvals, changed provider names/parent/capacity and revoked switches or accounts refuse execution. "
        "Native approval is required whatever the GUI synchronization threshold. Unknown commit never triggers an automatic replay. "
        "Names are untrusted literal data; credentials and raw provider errors are withheld."
    ),
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Owned destination, kind and real provider identity; no account or display-name override",
            schema=SourceLinkInput.model_json_schema(),
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
        "link a Drive folder to my knowledge space",
        "follow a Gmail label",
        "add a document source",
    ],
    display=DisplayMetadata(emoji="🔗", i18n_key="link_lia_knowledge_source", category="tool"),
)
