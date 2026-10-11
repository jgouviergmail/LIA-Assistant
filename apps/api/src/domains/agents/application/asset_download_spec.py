"""An exact generated-file download continues once in its original browser."""

from src.domains.agents.application.asset_download_schemas import AssetDownloadPatch
from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome

ASSET_DOWNLOAD_OPERATION = ApplicationOperationSpec(
    operation_id="generated_asset.download",
    tool_name="download_lia_generated_asset_tool",
    sections=("generated-assets",),
    input_model=AssetDownloadPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.DEVICE,
)
