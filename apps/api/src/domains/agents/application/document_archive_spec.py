"""A ZIP of exact selected personal documents resumes in the original browser."""

from src.domains.agents.application.document_archive_schemas import DocumentArchivePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

DOCUMENT_ARCHIVE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_documents.archive",
    tool_name="download_lia_knowledge_archive_tool",
    sections=("rag-spaces",),
    input_model=DocumentArchivePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
