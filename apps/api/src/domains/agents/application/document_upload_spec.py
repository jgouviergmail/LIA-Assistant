"""Approved native browser upload never accepts a host path or model-supplied file bytes."""

from src.domains.agents.application.document_upload_schemas import DocumentUploadPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.feature_switches.registry import PlatformCapability

DOCUMENT_UPLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_document.upload",
    tool_name="upload_lia_knowledge_document_tool",
    sections=("rag-spaces",),
    input_model=DocumentUploadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
