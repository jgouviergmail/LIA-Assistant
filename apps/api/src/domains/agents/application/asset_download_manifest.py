"""The model proposes an exact approved browser transfer, never storage paths or bytes."""

from src.domains.agents.application.asset_download_schemas import AssetDownloadInput
from src.domains.agents.application.asset_download_spec import ASSET_DOWNLOAD_OPERATION
from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

ASSET_DOWNLOAD_MANIFEST = ToolManifest(
    name=ASSET_DOWNLOAD_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to download one current-account generated image, document or screenshot from the gallery. Use an actual asset_id from get_lia_generated_gallery_tool. Exact public metadata and local descriptor identity are sealed and rechecked. Only a ready, present, regular owned file can transfer. The original active browser session requests the approved transfer once; expiry, hot switch and authority are checked again. Other sessions, stale files and uncertain acknowledgements refuse and never replay. The approved size bounds a temporary disk-backed copy. No byte contents or storage paths enter chat. Download requested does not prove reception or saving. Upload/generation/RAG switches do not hide existing gallery files. No generation, provider, embedding or paid model call; no retention or deletion.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact current-account generated artifact id",
            schema=AssetDownloadInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_generated_assets",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "download my generated image",
        "download gallery file",
        "save generated screenshot",
    ],
    display=DisplayMetadata(emoji="📥", i18n_key="download_lia_generated_asset", category="tool"),
)
