"""One confirmed exact subset; deleting synced projections does not unlink their source."""

from src.domains.agents.application.document_delete_schemas import DocumentDeletePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

DOCUMENT_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_documents.delete",
    tool_name="delete_lia_knowledge_documents_tool",
    sections=("rag-spaces",),
    input_model=DocumentDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
