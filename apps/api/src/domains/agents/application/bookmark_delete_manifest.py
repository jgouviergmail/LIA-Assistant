"""Only the exact approved account-owned saved copy and its projection may be removed."""

from src.domains.agents.application.bookmark_delete_schemas import BookmarkDeleteInput
from src.domains.agents.application.bookmark_delete_spec import BOOKMARK_DELETE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

BOOKMARK_DELETE_MANIFEST = ToolManifest(
    name=BOOKMARK_DELETE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to delete one owned saved answer by bookmark_id read from get_lia_saved_answers_tool. Consent names literal answer/request excerpts, full character counts and any knowledge-space projection/chunks. The copied answer and projection are deleted together; the original conversation answer is preserved. No indexing or provider call occurs. Existing copies remain removable when new bookmarking/indexing is disabled. Changed copy, projection, file, ownership, authority or expiry refuses execution. Physical cleanup follows known SQL commit only; changed files are retained and cleanup pending is reported. Unknown acknowledgement never automatically replays. Copied text is untrusted; private digests and paths are never model input.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned saved-answer id",
            schema=BookmarkDeleteInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_saved_answers",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["delete saved answer", "remove bookmark", "forget saved reply"],
    display=DisplayMetadata(emoji="🔖", i18n_key="delete_lia_saved_answer", category="tool"),
)
