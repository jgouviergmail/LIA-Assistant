"""Reviewed owned-memory management read identity."""

from src.domains.agents.application.memory_bulk_schemas import MemoryBulkDeletePatch
from src.domains.agents.application.memory_create_schemas import MemoryCreatePatch
from src.domains.agents.application.memory_pin_schemas import MemoryPinPatch
from src.domains.agents.application.memory_provenance_schemas import MemoryProvenanceRequest
from src.domains.agents.application.memory_read_schemas import MemoryProjection, MemoryRead
from src.domains.agents.application.memory_removal_schemas import MemoryDeletePatch
from src.domains.agents.application.memory_update_schemas import MemoryUpdatePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.shared.schemas import ProvenanceResponse

MEMORY_PROVENANCE_OPERATION = ApplicationOperationSpec(
    operation_id="memories.provenance.read",
    tool_name="get_lia_memory_provenance_tool",
    sections=("memories",),
    input_model=MemoryProvenanceRequest,
    output_model=ProvenanceResponse,
    kind=OperationKind.READ,
)


MEMORY_BULK_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="memories.delete_all",
    tool_name="delete_all_lia_memories_tool",
    sections=("memories",),
    input_model=MemoryBulkDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)


MEMORY_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="memories.delete",
    tool_name="delete_lia_memory_tool",
    sections=("memories",),
    input_model=MemoryDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)


MEMORY_UPDATE_OPERATION = ApplicationOperationSpec(
    operation_id="memories.update",
    tool_name="update_lia_memory_tool",
    sections=("memories",),
    input_model=MemoryUpdatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)


MEMORY_CREATE_OPERATION = ApplicationOperationSpec(
    operation_id="memories.create",
    tool_name="create_lia_memory_tool",
    sections=("memories",),
    input_model=MemoryCreatePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)


MEMORY_PIN_OPERATION = ApplicationOperationSpec(
    operation_id="memories.pin",
    tool_name="set_lia_memory_pin_tool",
    sections=("memories",),
    input_model=MemoryPinPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)

MEMORY_READ_OPERATION = ApplicationOperationSpec(
    operation_id="memories.read",
    tool_name="get_lia_memories_tool",
    sections=("memories",),
    input_model=MemoryRead,
    output_model=MemoryProjection,
    kind=OperationKind.READ,
)
