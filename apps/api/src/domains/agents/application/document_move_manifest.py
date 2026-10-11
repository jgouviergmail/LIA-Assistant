"""Both execution modes bind one bounded owned-document move with mandatory native consent."""

from src.domains.agents.application.document_move_schemas import DocumentMoveInput
from src.domains.agents.application.document_move_spec import DOCUMENT_MOVE_OPERATION
from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

DOCUMENT_MOVE_MANIFEST = ToolManifest(
    name=DOCUMENT_MOVE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to move exact selected uploaded document ids between two different owned knowledge spaces. Read real source/target ids with get_lia_knowledge_spaces_tool. Every selected document, source/target activation, exact chunks, target count/capacity and missing files are previewed; a whole preview above 64,000 bytes is refused, so select fewer. All selected documents must satisfy source movement rules. Drive/Gmail/meeting/saved-answer projections, pending processing, reindexing, foreign/system spaces, capacity overflow and existing destination files are refused. No move before approval. Fresh owner/native/RAG authority and exact source SQL/file state are checked under ordered account/space/document fences. Approved files are staged exclusively, source rows and chunks move atomically without re-embedding; inactive target documents no longer participate in retrieval. Local staging needs temporary disk space for the selected bytes. Originals remain through unknown SQL completion; unknown actions never automatically retry. After acknowledged move, original cleanup may remain pending. No provider/model/indexing call or past-cost refund. Names are literal data.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact source space, bounded document ids and different owned target space",
            schema=DocumentMoveInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_knowledge_spaces",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["move knowledge documents", "change document knowledge space"],
    display=DisplayMetadata(emoji="📂", i18n_key="move_lia_knowledge_documents", category="tool"),
)
