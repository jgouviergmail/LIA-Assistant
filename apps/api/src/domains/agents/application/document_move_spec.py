"""An exact owned document batch moves only after native human confirmation."""

from src.domains.agents.application.document_move_schemas import DocumentMovePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

DOCUMENT_MOVE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_documents.move",
    tool_name="move_lia_knowledge_documents_tool",
    sections=("rag-spaces",),
    input_model=DocumentMovePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
