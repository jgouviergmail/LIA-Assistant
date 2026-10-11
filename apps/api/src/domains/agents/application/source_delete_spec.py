"""Removing a source and its indexed data is an explicit destructive native action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.source_delete_schemas import SourceDeletePatch
from src.domains.feature_switches.registry import PlatformCapability

SOURCE_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_source.delete",
    tool_name="delete_lia_knowledge_source_tool",
    sections=("rag-spaces",),
    input_model=SourceDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
