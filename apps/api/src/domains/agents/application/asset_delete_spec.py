"""Generated-file deletion is an exact mandatory-confirmation native action."""

from src.domains.agents.application.asset_delete_schemas import AssetDeletePatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

ASSET_DELETE_OPERATION = ApplicationOperationSpec(
    operation_id="generated_assets.delete",
    tool_name="delete_lia_generated_assets_tool",
    sections=("generated-assets",),
    input_model=AssetDeletePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
