"""A memories export attached in the chat may be imported, as the settings allow (wave 2, lot 24)."""

from src.domains.agents.application.memory_import_schemas import MemoryImportPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

MEMORY_IMPORT_OPERATION = ApplicationOperationSpec(
    operation_id="memories.import",
    tool_name="import_lia_memories_tool",
    sections=("memories",),
    input_model=MemoryImportPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
