"""An owned source file transfer resumes once in its originally approved browser."""

from src.domains.agents.application.document_download_schemas import DocumentDownloadPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

DOCUMENT_DOWNLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_document.download",
    tool_name="download_lia_knowledge_document_tool",
    sections=("rag-spaces",),
    input_model=DocumentDownloadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
