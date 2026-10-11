"""Read export metadata and propose distinct, exactly confirmed export operations."""

from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

EXPORT_DOWNLOAD_MANIFEST = ToolManifest(
    name="download_lia_account_export_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to start a download of one owned available account-export archive. Read the latest job id and download_available first. Preview fixes its exact file identity, metadata and retention deadline. No bytes or audit count change before approval. The original authenticated browser then starts the finite, single-use transfer; other sessions, changed/expired/missing archives and operator withdrawal refuse it. No extra password flow is invented. Starting a request never proves that a file was saved to the device. No paths, credentials, archive contents or arbitrary URL in chat; never automatically replay an uncertain download.",
    parameters=[
        ParameterSchema(
            name="selection",
            type="object",
            required=True,
            description="One exact owned export job id",
            schema=ExportDownloadRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact download confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_account_export",
    initiative_eligible=False,
    semantic_keywords=["download my account export", "download my personal account archive"],
    display=DisplayMetadata(emoji="📦", i18n_key="download_lia_account_export", category="tool"),
)


EXPORT_READ_MANIFEST = ToolManifest(
    name="get_lia_account_export_tool",
    agent="setting_agent",
    description="Read whether account exports are enabled, the latest owned export job status/timestamps/size/error classification and download_available. A saved done status does not guarantee availability: retention must be valid and the file present. Never expose paths or archive contents, queue a new job, download, or increment audit counts. Request and download use separate exactly confirmed tools; download_lia_account_export_tool takes the available owned job id.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="enabled", type="boolean", description="Export feature availability"
        ),
        OutputFieldSchema(
            path="latest", type="object", nullable=True, description="Latest owned saved job"
        ),
        OutputFieldSchema(
            path="download_available",
            type="boolean",
            description="Current retention/file availability",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_account_export",
    semantic_keywords=["my account export", "is my export ready", "export availability"],
    display=DisplayMetadata(emoji="📦", i18n_key="get_lia_account_export", category="tool"),
)

EXPORT_REQUEST_MANIFEST = ToolManifest(
    name="request_lia_account_export_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation for a full-account export. The authenticated originating browser must then reauthenticate securely; no job starts during preparation or the first confirmation. The archive contains personal data and is built asynchronously. One active export per account; a queued job is never a ready archive. Read get_lia_account_export_tool for status, then propose download_lia_account_export_tool when download_available is true. No credentials, archive content or filesystem paths in chat. Observe a lost completion without automatically replaying the request.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending confirmation and secure browser handoff",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="create",
    binding_unit="lia_account_export",
    initiative_eligible=False,
    semantic_keywords=["request my account export", "export all my personal account data"],
    display=DisplayMetadata(emoji="📦", i18n_key="request_lia_account_export", category="tool"),
)
