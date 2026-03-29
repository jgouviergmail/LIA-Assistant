"""
LangGraph BaseStore singleton factory for Tool Context Management + Long-Term Memory.

Implements LangGraph best practice: global AsyncPostgresStore instance shared
across all agent executions for tool context persistence AND semantic memory.

Pattern:
    - Singleton AsyncPostgresStore (similar to checkpointer.py pattern)
    - PostgreSQL-backed for persistence across restarts
    - Semantic search via OpenAI text-embedding-3-small (1536 dims)
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

V3 (OpenAI Embeddings - 2026-03):
    - OpenAI text-embedding-3-small (1536 dims) via TrackedOpenAIEmbeddings
    - Shared singleton with tool routing and interest deduplication
    - Token tracking via Prometheus metrics
    - Replaces local E5 model to save ~1 GB RAM per worker

References:
    - LangGraph Store docs: https://langchain-ai.github.io/langgraph/reference/store/
    - LangGraph Semantic Search: https://blog.langchain.com/semantic-search-for-langgraph-memory/
    - Similar pattern: src/domains/conversations/checkpointer.py
"""

from langgraph.store.postgres import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Lazy import to avoid circular dependencies and startup cost
_embeddings_model = None


def _get_embeddings_model():
    """
    Lazy-load embeddings model for semantic search.

    Uses OpenAI text-embedding-3-small via TrackedOpenAIEmbeddings singleton,
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
            provider="openai",
        )

    return _embeddings_model


# Global Store instance and connection (initialized on first access)
_tool_context_store: AsyncPostgresStore | None = None
_store_connection: AsyncConnection | None = None


async def get_tool_context_store() -> AsyncPostgresStore:
    """
    Get or create global AsyncPostgresStore for tool context AND long-term memory.

    LangGraph best practice (2025):
    - Single Store instance shared across graph executions
    - PostgreSQL-backed for persistence across API restarts
    - Semantic search enabled via OpenAI embeddings
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
    global _tool_context_store, _store_connection

    if _tool_context_store is None:
        logger.info("tool_context_store_initializing")

        # Convert asyncpg URL to psycopg3 URL (same as checkpointer.py)
        database_url_str = str(settings.database_url)
        psycopg_url = database_url_str.replace("postgresql+asyncpg://", "postgresql://")

        # Create persistent connection for store
        _store_connection = await AsyncConnection.connect(
            psycopg_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,  # type: ignore[arg-type]
        )

        # Build index configuration for semantic search
        # NOTE: Memory/semantic search is always enabled (OpenAI embeddings)
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
                provider="openai",
            )
        except Exception as e:
            logger.warning(
                "semantic_search_config_failed",
                error=str(e),
                message="Falling back to non-semantic store",
            )

        # Create store with persistent connection and optional semantic index
        if index_config:
            _tool_context_store = AsyncPostgresStore(
                conn=_store_connection,  # type: ignore[arg-type]
                index=index_config,
            )
        else:
            _tool_context_store = AsyncPostgresStore(conn=_store_connection)  # type: ignore[arg-type]

        # Setup store tables (idempotent) - includes pgvector index if semantic enabled
        await _tool_context_store.setup()

        logger.info(
            "tool_context_store_initialized",
            store_type="AsyncPostgresStore",
            semantic_search=semantic_search_enabled,
            persistence=True,
            tables_created=["store_items", "store_metadata"],
        )

    return _tool_context_store


async def cleanup_tool_context_store() -> None:
    """
    Cleanup tool context store on application shutdown.

    Closes connection pool gracefully to avoid hanging connections.

    Usage:
        Add to FastAPI lifespan shutdown hook (already done in main.py)
    """
    global _tool_context_store, _store_connection

    if _tool_context_store is not None:
        logger.info("tool_context_store_cleanup_started")

        # Close the persistent psycopg connection
        if _store_connection is not None:
            await _store_connection.close()
            _store_connection = None

        _tool_context_store = None
        logger.info("tool_context_store_cleanup_completed")


def reset_tool_context_store() -> None:
    """
    Reset global tool context store (for testing only).

    WARNING: Only use in tests to force recreation of store.
    Production code should never call this method.

    This method clears the global singleton, forcing a new store
    to be created on next access. Useful for test isolation.
    """
    global _tool_context_store, _store_connection
    _tool_context_store = None
    _store_connection = None
    logger.warning("tool_context_store_reset")
