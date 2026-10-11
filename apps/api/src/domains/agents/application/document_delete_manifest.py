"""Both modes offer a closed exact subset under mandatory native confirmation."""

from src.domains.agents.application.document_delete_schemas import DocumentDeleteInput
from src.domains.agents.application.document_delete_spec import DOCUMENT_DELETE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

DOCUMENT_DELETE_MANIFEST = ToolManifest(
    name=DOCUMENT_DELETE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to delete exact selected document ids from one owned personal knowledge space. First read real ids and source types with get_lia_knowledge_spaces_tool. Preview includes the space, every selected name/status/source type/size and the exact indexed chunk count. No deletion before approval. Entire selection must satisfy source rights and deletion constraints; active processing/reindexing or linked source sync requires waiting. Saved-answer projections must be removed through their bookmark record. Deleting a Drive, Gmail or meeting projection does not unlink its source or delete the provider original; future synchronization may recreate it. Confirmed deletion rechecks fresh full SQL/file identities under owner/space/source/document locks, deletes source rows transactionally and verifies the exact cascade. Local cleanup follows acknowledged commit only and can remain pending. No indexing or model call; past usage is not refunded. Unknown completion is never retried. Foreign and system/admin spaces unavailable; names are literal data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned space and selected real ids under source batch bound",
            schema=DocumentDeleteInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_knowledge_spaces",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["delete selected knowledge-space documents", "remove indexed files"],
    display=DisplayMetadata(emoji="🗑️", i18n_key="delete_lia_knowledge_documents", category="tool"),
)
