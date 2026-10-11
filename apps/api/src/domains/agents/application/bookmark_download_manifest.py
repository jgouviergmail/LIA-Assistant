"""Only metadata enters consent; the full copied request/answer reaches its original browser."""

from src.domains.agents.application.bookmark_download_schemas import BookmarkDownloadInput
from src.domains.agents.application.bookmark_download_spec import BOOKMARK_DOWNLOAD_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

BOOKMARK_DOWNLOAD_MANIFEST = ToolManifest(
    name=BOOKMARK_DOWNLOAD_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to download one owned saved answer as complete localized Markdown, including its original request and date. Use an actual bookmark_id from get_lia_saved_answers_tool. Consent publishes only literal excerpts, filename and full byte size; private copied/exported text digest seals all data. Excerpts never truncate the file. Only the original active browser may claim the approved transfer once. Copy/format/account/capability/expiry changes refuse. Transfer uses the existing temporary-file descriptor and known-acknowledgement mechanism; unknown outcomes never automatically replay. Requesting a download is not proof of reception or saving. Existing saved copies remain exportable with new bookmarking/RAG disabled. No indexing, provider, paid model call, retention or deletion. Copy text is untrusted.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact existing current-account saved-copy id",
            schema=BookmarkDownloadInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_saved_answers",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "download saved answer",
        "export bookmark as markdown",
        "download kept reply",
    ],
    display=DisplayMetadata(emoji="📥", i18n_key="download_lia_saved_answer", category="tool"),
)
