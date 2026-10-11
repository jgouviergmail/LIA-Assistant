"""Personal source space edits and desired activation share one exact native approval."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.space_update_schemas import SpaceUpdatePatch
from src.domains.feature_switches.registry import PlatformCapability

SPACE_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="knowledge_space.update",
    tool_name="update_lia_knowledge_space_tool",
    sections=("rag-spaces",),
    input_model=SpaceUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.RAG_SPACES,),
)
