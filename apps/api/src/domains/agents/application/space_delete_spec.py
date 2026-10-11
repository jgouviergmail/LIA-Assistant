"""Personal-space deletion is one native confirmed action, never an administrator operation."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.space_delete_schemas import SpaceDeletePatch
from src.domains.feature_switches.registry import PlatformCapability

SPACE_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_space.delete",
    tool_name="delete_lia_knowledge_space_tool",
    sections=("rag-spaces",),
    input_model=SpaceDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
