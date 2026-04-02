"""
RAG Spaces retrieval service.

Performs hybrid search (semantic + BM25) across user's active spaces
or system spaces, and returns formatted context for prompt injection.

Supports two modes:
- User mode: searches user-owned spaces (default)
- System mode: searches system spaces (FAQ, app knowledge) via system_only=True

Standalone service importable from any LangGraph node.

Phase: evolution — RAG Spaces (User Knowledge Documents)
Created: 2026-03-14
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from uuid import UUID

import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.rag_spaces.embedding import get_rag_embeddings
from src.domains.rag_spaces.repository import RAGChunkRepository, RAGSpaceRepository
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_rag_spaces import (
    rag_retrieval_chunks_returned,
    rag_retrieval_duration_seconds,
    rag_retrieval_requests_total,
    rag_retrieval_skipped_total,
    rag_system_retrieval_total,
)
from src.infrastructure.store.bm25_index import get_bm25_manager, tokenize_text

logger = get_logger(__name__)

# Tiktoken encoding for token counting (cl100k_base used for token budgeting)
_TIKTOKEN_ENCODING = "cl100k_base"


@dataclass
class RAGRetrievedChunk:
    """A single retrieved chunk with metadata."""

    content: str
    score: float
    space_name: str
    original_filename: str
    chunk_index: int


@dataclass
class RAGContext:
    """Result of RAG retrieval across user's or system's active spaces."""

    chunks: list[RAGRetrievedChunk] = field(default_factory=list)
    spaces_searched: int = 0
    total_results: int = 0
    context_type: str = "user"  # "user" or "system"

    def to_prompt_context(self) -> str:
        """Format retrieved chunks as prompt context for injection."""
        if not self.chunks:
            return ""

        if self.context_type == "system":
            lines = [
                "## APP KNOWLEDGE (FAQ / Help)\n",
                "The following information comes from LIA's built-in knowledge base.",
                "Use it to answer questions about the app, its features, and usage.\n",
            ]
        else:
            lines = [
                "## USER KNOWLEDGE SPACES (RAG Documents)\n",
                "The following information comes from the user's personal document spaces.",
                "Use it to enrich your response when relevant to the question.",
                "Always cite the source document when using this information.\n",
            ]

        for chunk in self.chunks:
            lines.append(f"[Space: {chunk.space_name}]")
            lines.append(f"Source: {chunk.original_filename}")
            lines.append(chunk.content)
            lines.append("---\n")

        return "\n".join(lines)

    def truncate_to_token_budget(self, max_tokens: int) -> RAGContext:
        """Truncate chunks to fit within a token budget."""
        if not self.chunks:
            return self

        try:
            encoding = tiktoken.get_encoding(_TIKTOKEN_ENCODING)
        except Exception:
            # Fallback: rough estimate 4 chars per token
            encoding = None

        truncated: list[RAGRetrievedChunk] = []
        total_tokens = 0
        # Header overhead (~50 tokens)
        header_overhead = 50

        for chunk in self.chunks:
            if encoding:
                chunk_tokens = len(encoding.encode(chunk.content))
            else:
                chunk_tokens = len(chunk.content) // 4

            if total_tokens + chunk_tokens + header_overhead > max_tokens:
                break

            truncated.append(chunk)
            total_tokens += chunk_tokens

        return RAGContext(
            chunks=truncated,
            spaces_searched=self.spaces_searched,
            total_results=self.total_results,
            context_type=self.context_type,
        )


async def retrieve_rag_context(
    user_id: UUID | None,
    query: str,
    db: AsyncSession,
    system_only: bool = False,
    limit: int | None = None,
    min_score: float | None = None,
    max_context_tokens: int | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> RAGContext | None:
    """
    Retrieve relevant RAG context for a user query.

    Performs hybrid search (semantic + BM25) across active spaces.
    Returns None if no active spaces or no relevant results.

    Args:
        user_id: User UUID for user spaces, or None for system spaces.
        query: User's query text.
        db: Database session.
        system_only: If True, search system spaces only (ignores user_id).
        limit: Max chunks to return (default from settings).
        min_score: Minimum hybrid score threshold (default from settings).
        max_context_tokens: Token budget for RAG context (default from settings).
        session_id: Session ID for embedding cost tracking.
        conversation_id: Conversation ID for embedding cost tracking.
        run_id: Optional run ID to merge embedding costs into the
            conversation's existing TrackingContext (MessageTokenSummary).

    Returns:
        RAGContext with retrieved chunks, or None if nothing relevant
    """
    limit = limit or settings.rag_spaces_retrieval_limit
    min_score = min_score if min_score is not None else settings.rag_spaces_retrieval_min_score
    max_context_tokens = max_context_tokens or settings.rag_spaces_max_context_tokens
    alpha = settings.rag_spaces_hybrid_alpha

    space_repo = RAGSpaceRepository(db)
    chunk_repo = RAGChunkRepository(db)

    # 1. Get active spaces (user or system)
    if system_only:
        active_spaces = await space_repo.get_active_system_spaces()
        context_type = "system"
        log_user_id = "system"
    else:
        if user_id is None:
            raise ValueError("user_id is required when system_only=False")
        active_spaces = await space_repo.get_active_for_user(user_id)
        context_type = "user"
        log_user_id = str(user_id)

    if not active_spaces:
        logger.debug("rag_retrieval_no_active_spaces", user_id=log_user_id)
        if system_only:
            rag_system_retrieval_total.labels(has_results="false").inc()
        else:
            rag_retrieval_skipped_total.labels(reason="no_active_spaces").inc()
        return None

    active_space_ids = [s.id for s in active_spaces]
    space_name_map = {s.id: s.name for s in active_spaces}
    retrieval_start = time.time()

    # 2. Check if reindexing is in progress (user spaces only)
    if not system_only:
        try:
            from src.infrastructure.cache.redis import get_redis_cache

            redis = await get_redis_cache()
            from src.domains.rag_spaces.reindex import REINDEX_FLAG_KEY

            if await redis.get(REINDEX_FLAG_KEY):
                logger.warning("rag_retrieval_reindex_in_progress", user_id=log_user_id)
                rag_retrieval_skipped_total.labels(reason="reindex_in_progress").inc()
                return None
        except Exception as e:
            # Redis unavailable — continue without reindex check (graceful degradation)
            logger.warning("rag_retrieval_redis_unavailable", error=str(e))

    # 3. Set embedding tracking context
    embedding_user_id = "system" if system_only else str(user_id)
    set_embedding_context(
        user_id=embedding_user_id,
        session_id=session_id or ("system_rag_search" if system_only else "rag_search"),
        conversation_id=conversation_id,
        run_id=run_id,
    )

    # Determine user_id for chunk queries (None for system spaces)
    chunk_user_id = None if system_only else user_id

    try:
        # 4. Embed the query
        embeddings = get_rag_embeddings()
        query_embedding = await embeddings.aembed_query(query)

        # 5. Semantic search via pgvector
        semantic_results = await chunk_repo.search_by_similarity(
            user_id=chunk_user_id,
            space_ids=active_space_ids,
            query_embedding=query_embedding,
            limit=limit * 3,  # Over-fetch for hybrid fusion
        )

        if not semantic_results:
            logger.debug(
                "rag_retrieval_no_semantic_results",
                user_id=log_user_id,
                spaces_searched=len(active_space_ids),
            )
            return RAGContext(
                chunks=[],
                spaces_searched=len(active_space_ids),
                total_results=0,
                context_type=context_type,
            )

        # 6. BM25 scoring
        bm25_scores_map: dict[UUID, float] = {}
        bm25_cache_key = "rag:system" if system_only else f"rag:{user_id}"
        try:
            corpus_data = await chunk_repo.get_corpus_for_spaces(chunk_user_id, active_space_ids)
            if corpus_data:
                corpus_texts = [text for _, text in corpus_data]
                corpus_ids = [str(cid) for cid, _ in corpus_data]

                bm25_manager = get_bm25_manager()
                bm25, bm25_ids = bm25_manager.get_or_build_index(
                    user_id=bm25_cache_key,
                    documents=corpus_texts,
                    document_ids=corpus_ids,
                )
                query_tokens = tokenize_text(query)
                raw_scores = bm25.get_scores(query_tokens)

                # Normalize BM25 scores to [0, 1] — cast to float() to avoid numpy.float64
                max_bm25 = (
                    float(max(raw_scores))
                    if len(raw_scores) > 0 and float(max(raw_scores)) > 0
                    else 1.0
                )
                for idx, score in enumerate(raw_scores):
                    chunk_id = UUID(bm25_ids[idx])
                    bm25_scores_map[chunk_id] = float(score) / max_bm25
        except Exception as e:
            logger.warning("rag_bm25_scoring_failed", error=str(e))

        # 7. Hybrid fusion
        scored_chunks: list[tuple[RAGRetrievedChunk, float]] = []
        for chunk, semantic_score in semantic_results:
            # semantic_score is already a similarity score [0, 1] from repository
            bm25_score = bm25_scores_map.get(chunk.id, 0.0)

            hybrid_score = float(alpha * semantic_score + (1 - alpha) * bm25_score)

            if hybrid_score < min_score:
                continue

            metadata = chunk.metadata_ or {}
            scored_chunks.append(
                (
                    RAGRetrievedChunk(
                        content=chunk.content,
                        score=round(hybrid_score, 4),
                        space_name=space_name_map.get(chunk.space_id, "Unknown"),
                        original_filename=metadata.get("original_filename", "unknown"),
                        chunk_index=chunk.chunk_index,
                    ),
                    hybrid_score,
                )
            )

        # Sort by score descending and take top N
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        top_chunks = [chunk for chunk, _ in scored_chunks[:limit]]

        context = RAGContext(
            chunks=top_chunks,
            spaces_searched=len(active_space_ids),
            total_results=len(scored_chunks),
            context_type=context_type,
        )

        # 8. Truncate to token budget
        context = context.truncate_to_token_budget(max_context_tokens)

        # Prometheus metrics
        retrieval_duration = time.time() - retrieval_start
        has_results = len(context.chunks) > 0
        if system_only:
            rag_system_retrieval_total.labels(has_results=str(has_results).lower()).inc()
        else:
            rag_retrieval_requests_total.labels(has_results=str(has_results).lower()).inc()
        rag_retrieval_duration_seconds.observe(retrieval_duration)
        rag_retrieval_chunks_returned.observe(len(context.chunks))
        # Note: search embedding token count tracked by GeminiRetrievalEmbeddings globally

        logger.info(
            "rag_retrieval_complete",
            user_id=log_user_id,
            system_only=system_only,
            spaces_searched=len(active_space_ids),
            semantic_results=len(semantic_results),
            hybrid_above_threshold=len(scored_chunks),
            chunks_returned=len(context.chunks),
        )

        return context

    finally:
        # 9. Always clear embedding context
        clear_embedding_context()
