"""Knowledge-space creation is an exact human-confirmed, source-owned action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.space_create_schemas import SpaceCreatePatch
from src.domains.feature_switches.registry import PlatformCapability

SPACE_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_space.create",
    tool_name="create_lia_knowledge_space_tool",
    sections=("rag-spaces",),
    input_model=SpaceCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
