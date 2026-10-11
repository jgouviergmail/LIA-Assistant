"""A manual sync is always human-approved and reports acceptance before indexing."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.source_sync_schemas import SourceSyncPatch
from src.domains.feature_switches.registry import PlatformCapability

SOURCE_SYNC_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_source.sync",
    tool_name="sync_lia_knowledge_source_tool",
    sections=("rag-spaces",),
    input_model=SourceSyncPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
