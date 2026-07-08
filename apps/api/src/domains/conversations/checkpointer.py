"""
PostgreSQL checkpointer factory for LangGraph state persistence.

Implements LangGraph best practice: global connection pool with single checkpointer
instance shared across all graph executions (ADR-111). Each checkpoint operation
checks out its own connection from an `AsyncConnectionPool`, so concurrent
conversations of a worker no longer queue on a single connection (audit S2/A7).

Uses InstrumentedAsyncPostgresSaver to add Prometheus metrics tracking for:
- Checkpoint save/load duration (detect slow writes/reads)
- Checkpoint payload size (detect conversation bloat)
- Operation success/failure rates (detect reliability issues)
- Error categorization (db_connection/serialization/timeout/permission)

Phase 3.3 Metrics (5 total):
- checkpoint_save_duration_seconds{node_name}
- checkpoint_load_duration_seconds{node_name}
- checkpoint_size_bytes{node_name}
- checkpoint_operations_total{operation, status}
- checkpoint_errors_total{error_type, operation}

References:
- LangGraph persistence docs: https://langchain-ai.github.io/langgraph/how-tos/persistence/
- ADR-111: LangGraph Postgres connection pooling (pool sizing & connection budget)
"""

import asyncio
from typing import cast

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.core.config import settings
from src.domains.conversations.instrumented_checkpointer import (
    InstrumentedAsyncPostgresSaver,
)
from src.infrastructure.observability.logging import get_logger

# Custom types serialized in checkpoint state (msgpack).
# langgraph-checkpoint 4.0+ requires explicit allowlisting to deserialize
# custom application types. Without this, deserialization warnings are logged
# and will become hard errors in a future version.
#
# MAINTAINER NOTE: Only dataclasses and Enums need allowlisting here.
# Pydantic BaseModels serialize as native dicts and don't trigger this.
# When adding a new dataclass or Enum to the graph state (MessagesState),
# add it here. Monitor logs for "Deserializing unregistered type" warnings
# to detect missing entries.
_CHECKPOINT_ALLOWED_MODULES: list[tuple[str, str]] = [
    # --- Graph state: routing & analysis ---
    ("src.domains.agents.domain_schemas", "RouterOutput"),
    ("src.domains.agents.analysis.query_intelligence", "QueryIntelligence"),
    ("src.domains.agents.analysis.query_intelligence", "UserGoal"),
    # --- Graph state: orchestration ---
    ("src.domains.agents.orchestration.plan_schemas", "ExecutionPlan"),
    ("src.domains.agents.orchestration.plan_schemas", "StepType"),
    ("src.domains.agents.orchestration.semantic_validator", "CriticalityLevel"),
    ("src.domains.agents.orchestration.semantic_validator", "SemanticValidationResult"),
    ("src.domains.agents.orchestration.semantic_validator", "SemanticIssueType"),
    ("src.domains.agents.orchestration.validator", "ValidationIssue"),
    ("src.domains.agents.orchestration.validator", "ValidationResult"),
    # --- Graph state: planning & catalogue ---
    ("src.domains.agents.services.planner.planning_result", "PlanningResult"),
    ("src.domains.agents.services.smart_catalogue_service", "FilteredCatalogue"),
    # --- Graph state: tools & references ---
    ("src.domains.agents.tools.common", "ToolErrorCode"),
    ("src.domains.agents.data_registry.models", "RegistryItemType"),
    ("src.domains.agents.services.reference_resolver", "ResolvedContext"),
]

logger = get_logger(__name__)

# Global checkpointer instance and connection pool (initialized on first access)
_checkpointer: InstrumentedAsyncPostgresSaver | None = None
_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None


async def get_checkpointer() -> InstrumentedAsyncPostgresSaver:
    """
    Get or create global InstrumentedAsyncPostgresSaver instance.

    LangGraph best practice:
    - Single checkpointer instance backed by a shared connection pool
    - No internal state kept by graph or checkpointer
    - Each checkpoint operation checks out its own pooled connection, so
      concurrent conversations don't serialize on a single connection (ADR-111)

    The instrumented checkpointer automatically:
    - Creates checkpoint tables on first setup (idempotent)
    - Stores state differentially (only changed values)
    - Versions each channel separately
    - Uses thread_id for conversation isolation
    - Tracks Prometheus metrics (save duration, payload size)

    Returns:
        Configured InstrumentedAsyncPostgresSaver ready for graph.compile(checkpointer=...)

    Example:
        >>> checkpointer = await get_checkpointer()
        >>> graph = build_graph(checkpointer=checkpointer)
        >>> config = RunnableConfig(configurable={"thread_id": str(conversation_id)})
        >>> result = await graph.ainvoke(state, config)

    Notes:
        - Setup is idempotent and runs once per process (singleton guard)
        - Connection string uses psycopg3 (not asyncpg) driver
        - Pool sizes come from settings (LANGGRAPH_CHECKPOINT_POOL_MIN/MAX_SIZE)
        - Tables created: checkpoints, checkpoint_blobs, checkpoint_writes
        - Metrics exposed: checkpoint_save_duration_seconds, checkpoint_size_bytes
    """
    global _checkpointer, _pool

    if _checkpointer is None:
        logger.info(
            "checkpointer_initializing",
            instrumented=True,
            pool_min_size=settings.langgraph_checkpoint_pool_min_size,
            pool_max_size=settings.langgraph_checkpoint_pool_max_size,
        )

        # Convert asyncpg URL to psycopg3 URL
        # asyncpg format: postgresql+asyncpg://user:pass@host/db
        # psycopg3 format: postgresql://user:pass@host/db
        # Convert MultiHostUrl to string first
        database_url_str = str(settings.database_url)
        psycopg_url = database_url_str.replace("postgresql+asyncpg://", "postgresql://")

        # Connection pool shared by all graph executions of this worker (ADR-111).
        # Connection kwargs are identical to the former single AsyncConnection and
        # to upstream AsyncPostgresSaver.from_conn_string: autocommit=True (setup
        # migrations), prepare_threshold=0 and dict_row (required by the saver).
        # check= validates connections on checkout (parity with SQLAlchemy
        # pool_pre_ping=True): a connection killed while idle (PG restart) is
        # replaced instead of failing the checkpoint operation.
        # The cast mirrors upstream (store aio.py): psycopg_pool's constructor is
        # not generic over connection kwargs, but every connection it creates uses
        # row_factory=dict_row.
        pool = cast(
            AsyncConnectionPool[AsyncConnection[DictRow]],
            AsyncConnectionPool(
                psycopg_url,
                min_size=settings.langgraph_checkpoint_pool_min_size,
                max_size=settings.langgraph_checkpoint_pool_max_size,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": 0,
                    "row_factory": dict_row,
                },
                check=AsyncConnectionPool.check_connection,
                open=False,
            ),
        )
        # Fail fast at startup: wait until min_size connections are established
        # (raises PoolTimeout and closes the pool if the database is unreachable).
        await pool.open(wait=True, timeout=settings.database_pool_timeout)
        _pool = pool

        try:
            # Create INSTRUMENTED checkpointer on the pool. The wrapper adds
            # Prometheus metrics and the pool-aware _cursor override (ADR-111).
            serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
            _checkpointer = InstrumentedAsyncPostgresSaver(conn=pool, serde=serde)

            # Setup checkpoint tables (idempotent)
            await _checkpointer.setup()
        except Exception:
            # Don't leak an opened pool if setup fails: next call re-enters init.
            await pool.close()
            _pool = None
            _checkpointer = None
            raise

        logger.info(
            "checkpointer_initialized",
            tables_created=["checkpoints", "checkpoint_blobs", "checkpoint_writes"],
            instrumented=True,
            pooled=True,
            metrics_exposed=[
                "checkpoint_save_duration_seconds",
                "checkpoint_load_duration_seconds",
                "checkpoint_size_bytes",
                "checkpoint_operations_total",
                "checkpoint_errors_total",
            ],
        )

    return _checkpointer


async def cleanup_checkpointer() -> None:
    """
    Cleanup checkpointer on application shutdown.

    Closes the connection pool gracefully: in-flight connections are closed as
    they return to the pool, remaining workers are terminated after the pool's
    close timeout.

    Usage:
        Add to FastAPI lifespan shutdown hook:
        >>> @asynccontextmanager
        >>> async def lifespan(app: FastAPI):
        >>>     yield
        >>>     await cleanup_checkpointer()
    """
    global _checkpointer, _pool

    if _checkpointer is not None or _pool is not None:
        logger.info("checkpointer_cleanup_started")

        if _pool is not None:
            await _pool.close()
            _pool = None

        _checkpointer = None
        logger.info("checkpointer_cleanup_completed")


def reset_checkpointer() -> None:
    """
    Reset global checkpointer (for testing only).

    Clears the singleton so the next get_checkpointer() call rebuilds it.
    The previous pool is closed best-effort: as a background task when an event
    loop is running, abandoned otherwise (acceptable in test teardown; prefer
    `await cleanup_checkpointer()` from async code).

    WARNING: Only use in tests to force recreation of checkpointer.
    """
    global _checkpointer, _pool
    if _pool is not None:
        pool = _pool
        try:
            asyncio.get_running_loop().create_task(
                pool.close(), name="checkpointer_pool_close_on_reset"
            )
        except RuntimeError:
            # No running loop (sync context): abandon the pool; connections are
            # reclaimed at process exit. Test-only path, mirrors previous behavior.
            pass
    _checkpointer = None
    _pool = None
