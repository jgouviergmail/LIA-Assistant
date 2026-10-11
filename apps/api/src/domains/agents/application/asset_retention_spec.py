"""Retaining generated files is a mandatory-confirmation account action."""

from src.domains.agents.application.asset_retention_schemas import AssetRetentionPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

ASSET_RETENTION_OPERATION = ApplicationOperationSpec(
    operation_id="generated_assets.retention.update",
    tool_name="update_lia_generated_asset_retention_tool",
    sections=("generated-assets",),
    input_model=AssetRetentionPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
)
