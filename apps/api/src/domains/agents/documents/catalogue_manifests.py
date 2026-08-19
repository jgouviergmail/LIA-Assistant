"""Catalogue manifests for Documents tools (P1, ADR-141).

User RAG spaces as an active routable capability. Internal, no OAuth,
read-only — the passive response-context injection is unchanged.
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# =============================================================================
# Agent Manifest: document_agent
# =============================================================================

DOCUMENT_AGENT_MANIFEST = AgentManifest(
    name="document_agent",
    description=(
        "Agent specialized in the user's own document spaces (uploaded PDFs, "
        "notes, synced files). Semantic search over their content: quotes, "
        "contracts, guides, personal knowledge. Read-only."
    ),
    tools=["search_user_documents_tool"],
    max_parallel_runs=2,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="📚",
        i18n_key="document_agent",
        visible=True,
        category="agent",
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: search_user_documents_tool
# =============================================================================

search_user_documents_catalogue_manifest = ToolManifest(
    name="search_user_documents_tool",
    agent="document_agent",
    description=(
        "Semantic (hybrid RAG) search over the USER'S OWN uploaded document "
        "spaces. Returns relevant excerpts with space, filename and score. "
        "Use for 'in my documents/notes/contracts/quotes' questions and to "
        "cross-check personal documents against emails or web results. NOT "
        "for cloud-drive file browsing (file domain) or the public web."
    ),
    parameters=[
        ParameterSchema(
            name="query",
            type="string",
            required=True,
            description=(
                "Semantic search query in the USER'S language (documents are "
                "stored as written — do not translate)."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=2),
                ParameterConstraint(kind="max_length", value=300),
            ],
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Max excerpts to return (1-10, default 5)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="documents",
            type="array",
            description="Excerpts: content, space, filename, score",
        ),
        OutputFieldSchema(
            path="documents[].content",
            type="string",
            description="Excerpt text from the user's uploaded file",
            # Verified against the real payload (documents_tools.py): the
            # excerpt IS file content. A document→file identity bridge would
            # need a `file_name` ontology type + a drive consumer — flagged
            # as follow-up (lot 4), not faked here.
            semantic_type="file_content",
        ),
        OutputFieldSchema(
            path="count",
            type="integer",
            description="Number of excerpts returned",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=60,
        est_tokens_out=400,
        est_cost_usd=0.0002,
        est_latency_ms=600,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "search inside my uploaded documents and notes",
        "what does my contract or quote document say",
        "find information in my personal knowledge spaces",
        "look up something in the files I gave you",
        "compare my document with another source",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="🔎",
        i18n_key="search_user_documents",
        visible=True,
        category="tool",
    ),
    tool_category="search",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
