"""The model chooses only a real destination; the original browser chooses and confirms bytes."""

from src.domains.agents.application.document_upload_schemas import DocumentUploadInput
from src.domains.agents.application.document_upload_spec import DOCUMENT_UPLOAD_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

DOCUMENT_UPLOAD_MANIFEST = ToolManifest(
    name=DOCUMENT_UPLOAD_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to import one local document into a real owned knowledge space. Obtain space_id with get_lia_knowledge_spaces_tool. Choose ONLY the destination; never supply a filename, host path, URL, bytes or base64. The original authenticated browser then lets the person choose a file and explicitly confirm its name, size and destination before sending it once. Current source MIME, size/capacity, owner, account, session, capabilities and expiry are checked again. System and foreign spaces unavailable. Inactive destination remains excluded from retrieval. Receipt confirms upload acceptance, never completed indexing; asynchronous source extraction/embedding uses platform quotas/rate limits and can incur billed tokens/costs. Processing progress and actual costs come from the knowledge-space reader. No provider call before file consent/commit. Unknown completion never automatically retries. File content and storage path never enter chat; names are literal data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact real owned space_id; file choice belongs to the browser",
            schema=DocumentUploadInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_knowledge_spaces",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["import my document", "upload a local file to my knowledge space"],
    display=DisplayMetadata(emoji="📤", i18n_key="upload_lia_knowledge_document", category="tool"),
)
