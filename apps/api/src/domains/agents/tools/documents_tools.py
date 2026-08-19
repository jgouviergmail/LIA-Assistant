"""Documents tools — the user's RAG spaces as an active capability (P1, ADR-141).

The passive last-message injection (``response_context``) remains; this tool
gives the planner/ReAct first-class access: derived queries, iteration, and
cross-domain combination ("compare the PDF quote with Paul's email").
Read-only, no HITL, no OAuth — the spaces belong to the user.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_DOCUMENT
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.decorators import read_tool, with_user_preferences
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config

logger = structlog.get_logger(__name__)

# Per-document excerpt cap injected back to the LLM (token budget guard).
_DOCUMENT_EXCERPT_CHARS = 600


@read_tool(name="search_user_documents", agent_name=AGENT_DOCUMENT)
@with_user_preferences
async def search_user_documents_tool(
    query: Annotated[
        str,
        "Semantic search query over the user's document spaces, in the "
        "user's language (their documents are stored as written).",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    max_results: Annotated[int, "Max document excerpts to return (1-10)"] = 5,
    user_timezone: str = "UTC",
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Search the user's uploaded document spaces by meaning (hybrid RAG).

    Args:
        query: Semantic query (kept in the user's language).
        runtime: LangChain tool runtime.
        max_results: Excerpt cap (bounded 1-10).
        user_timezone: Injected user timezone (unused, preference contract).
        locale: Injected user language (unused, preference contract).

    Returns:
        UnifiedToolOutput with ``{documents: [...], count}`` — each document
        carries content excerpt, space name, filename and relevance score.
    """
    config = validate_runtime_config(runtime, "search_user_documents_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    if not getattr(settings, "rag_spaces_enabled", False):
        return UnifiedToolOutput.failure(
            message="document spaces are not enabled on this deployment",
            error_code="documents_not_configured",
        )

    from src.domains.rag_spaces.retrieval import retrieve_rag_context
    from src.infrastructure.database.session import get_db_context

    bounded = max(1, min(int(max_results), 10))
    async with get_db_context() as db:
        rag_result = await retrieve_rag_context(
            user_id=UUID(config.user_id),
            query=query,
            db=db,
            limit=bounded,
        )

    documents = [
        {
            "content": (chunk.content or "")[:_DOCUMENT_EXCERPT_CHARS],
            "space": chunk.space_name,
            "filename": chunk.original_filename,
            "score": round(float(chunk.score), 3),
        }
        for chunk in (rag_result.chunks if rag_result else [])
    ]

    logger.info(
        "user_documents_searched",
        user_id=config.user_id,
        count=len(documents),
    )
    return UnifiedToolOutput.data_success(
        message=f"{len(documents)} document excerpt(s) found",
        structured_data={"documents": documents, "count": len(documents)},
    )
