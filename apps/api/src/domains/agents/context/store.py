"""
LangGraph BaseStore singleton factory for Tool Context Management + Long-Term Memory.

Implements LangGraph best practice: global AsyncPostgresStore instance shared
across all agent executions for tool context persistence AND semantic memory.

Pattern:
    - Singleton AsyncPostgresStore (similar to checkpointer.py pattern)
    - Backed by an AsyncConnectionPool: each store operation checks out its own
      connection instead of queueing on a single persistent one (ADR-111)
    - PostgreSQL-backed for persistence across restarts
    - Semantic search via Gemini gemini-embedding-001 (1536 dims)
    - Thread-safe, module-level singleton
    - Lazy initialization on first access

BUGFIX: Changed from InMemoryStore to AsyncPostgresStore to fix context
resolution regression where "affiche le detail de la premiere" failed because
contexts were lost on API restart (InMemoryStore has no persistence).

V2 (Long-Term Memory):
    - Semantic search enabled with pgvector HNSW index
    - Namespace hierarchy: (user_id, "memories") for user profile
    - Multi-field indexing: content, text, trigger_topic
    - LangMem integration ready

V3 (Gemini Embeddings - 2026-03):
    - Gemini gemini-embedding-001 (1536 dims) via GeminiRetrievalEmbeddings
    - Shared singleton with tool routing and interest deduplication
    - Token tracking via Prometheus metrics
    - Replaces local E5 model to save ~1 GB RAM per worker

References:
    - LangGraph Store docs: https://langchain-ai.github.io/langgraph/reference/store/
    - LangGraph Semantic Search: https://blog.langchain.com/semantic-search-for-langgraph-memory/
    - Similar pattern: src/domains/conversations/checkpointer.py
"""

import asyncio
from contextlib import suppress
from typing import cast

from langgraph.store.postgres import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Lazy import to avoid circular dependencies and startup cost
_embeddings_model = None


def _get_embeddings_model():
    """
    Lazy-load embeddings model for semantic search.

    Uses Gemini gemini-embedding-001 via GeminiRetrievalEmbeddings singleton,
    shared with tool routing and interest deduplication.

    Only initialized once on first access (singleton pattern).
    """
    global _embeddings_model

    if _embeddings_model is None:
        from src.infrastructure.llm.memory_embeddings import get_memory_embeddings

        _embeddings_model = get_memory_embeddings()
        logger.info(
            "embeddings_model_initialized",
            model=settings.memory_embedding_model,
            dimensions=settings.memory_embedding_dimensions,
            provider="gemini",
        )

    return _embeddings_model


# Global Store instance and connection pool (initialized on first access)
_tool_context_store: AsyncPostgresStore | None = None
_store_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None


async def get_tool_context_store() -> AsyncPostgresStore:
    """
    Get or create global AsyncPostgresStore for tool context AND long-term memory.

    LangGraph best practice (2025):
    - Single Store instance shared across graph executions
    - PostgreSQL-backed for persistence across API restarts
    - Semantic search enabled via Gemini embeddings
    - Namespace isolation per user/collection/domain
    - Automatic table creation on first setup (idempotent)

    The Store automatically:
    - Provides hierarchical namespaces for isolation
    - Supports get/put/search/delete operations
    - Persists to PostgreSQL for durability
    - Semantic search with vector embeddings (pgvector)

    Namespaces:
        - (user_id, "context", domain)    → Tool context (existing)
        - (user_id, "memories")           → Long-term user memory (new)
        - (user_id, "documents", source)  → Future RAG documents

    Returns:
        Configured AsyncPostgresStore ready for graph.compile(store=...)

    Example:
        >>> store = await get_tool_context_store()
        >>> graph = build_graph(checkpointer=checkpointer, store=store)
        >>> # Store is auto-injected into tools via `*, store: BaseStore` parameter
        >>> # Semantic search: results = await store.asearch((user_id, "memories"), query="...")
    """
    global _tool_context_store, _store_pool

    if _tool_context_store is None:
        logger.info(
            "tool_context_store_initializing",
            pool_min_size=settings.langgraph_store_pool_min_size,
            pool_max_size=settings.langgraph_store_pool_max_size,
        )

        # Convert asyncpg URL to psycopg3 URL (same as checkpointer.py)
        database_url_str = str(settings.database_url)
        psycopg_url = database_url_str.replace("postgresql+asyncpg://", "postgresql://")

        # Connection pool for the store (ADR-111). AsyncPostgresStore._cursor is
        # natively pool-aware: each operation checks out its own connection.
        # Connection kwargs match the former single AsyncConnection exactly.
        # check= validates connections on checkout (parity with SQLAlchemy
        # pool_pre_ping=True). The cast mirrors upstream (store aio.py).
        pool = cast(
            AsyncConnectionPool[AsyncConnection[DictRow]],
            AsyncConnectionPool(
                psycopg_url,
                min_size=settings.langgraph_store_pool_min_size,
                max_size=settings.langgraph_store_pool_max_size,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                check=AsyncConnectionPool.check_connection,
                open=False,
            ),
        )
        # Fail fast at startup: wait until min_size connections are established.
        await pool.open(wait=True, timeout=settings.database_pool_timeout)
        _store_pool = pool

        # Build index configuration for semantic search
        # NOTE: Memory/semantic search is always enabled (Gemini embeddings)
        index_config = None
        semantic_search_enabled = False

        try:
            embeddings = _get_embeddings_model()
            index_config = {
                "dims": settings.memory_embedding_dimensions,
                "embed": embeddings,
                # Multi-field indexing for memories and tool context
                "fields": ["content", "text", "trigger_topic", "memory"],
            }
            semantic_search_enabled = True
            logger.info(
                "semantic_search_config_ready",
                dims=settings.memory_embedding_dimensions,
                fields=index_config["fields"],
                provider="gemini",
            )
        except Exception as e:
            logger.warning(
                "semantic_search_config_failed",
                error=str(e),
                message="Falling back to non-semantic store",
            )

        try:
            # Create store on the pool, with optional semantic index
            if index_config:
                _tool_context_store = AsyncPostgresStore(conn=pool, index=index_config)
            else:
                _tool_context_store = AsyncPostgresStore(conn=pool)

            # Setup store tables (idempotent) - includes pgvector index if semantic enabled
            await _tool_context_store.setup()
        except Exception:
            # Don't leak an opened pool if setup fails: next call re-enters init.
            await pool.close()
            _store_pool = None
            _tool_context_store = None
            raise

        logger.info(
            "tool_context_store_initialized",
            store_type="AsyncPostgresStore",
            semantic_search=semantic_search_enabled,
            persistence=True,
            pooled=True,
            tables_created=["store_items", "store_metadata"],
        )

    return _tool_context_store


async def cleanup_tool_context_store() -> None:
    """
    Cleanup tool context store on application shutdown.

    Closes the connection pool gracefully: in-flight connections are closed as
    they return to the pool, remaining workers are terminated after the pool's
    close timeout.

    Usage:
        Add to FastAPI lifespan shutdown hook (already done in main.py)
    """
    global _tool_context_store, _store_pool

    if _tool_context_store is not None or _store_pool is not None:
        logger.info("tool_context_store_cleanup_started")

        if _store_pool is not None:
            await _store_pool.close()
            _store_pool = None

        _tool_context_store = None
        logger.info("tool_context_store_cleanup_completed")


def reset_tool_context_store() -> None:
    """
    Reset global tool context store (for testing only).

    WARNING: Only use in tests to force recreation of store.
    Production code should never call this method.

    This method clears the global singleton, forcing a new store to be created
    on next access. The previous pool is closed best-effort: as a background
    task when an event loop is running, abandoned otherwise (prefer
    `await cleanup_tool_context_store()` from async code).
    """
    global _tool_context_store, _store_pool
    if _store_pool is not None:
        pool = _store_pool
        # No running loop (sync context): abandon the pool; connections are
        # reclaimed at process exit. Test-only path, mirrors previous behavior.
        with suppress(RuntimeError):
            asyncio.get_running_loop().create_task(pool.close(), name="store_pool_close_on_reset")
    _tool_context_store = None
    _store_pool = None
    logger.warning("tool_context_store_reset")
