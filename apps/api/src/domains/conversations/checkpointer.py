"""
PostgreSQL checkpointer factory for LangGraph state persistence.

Implements LangGraph best practice: global connection pool with single checkpointer
instance shared across all graph executions.

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
- LangGraph v0.2 docs: https://langchain-ai.github.io/langgraph/how-tos/persistence/
- Best practice: Create global connection pool, pass to checkpointer on each request
"""

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg import AsyncConnection
from psycopg.rows import dict_row

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

# Global checkpointer instance and connection (initialized on first access)
_checkpointer: InstrumentedAsyncPostgresSaver | None = None
_connection: AsyncConnection | None = None


async def get_checkpointer() -> InstrumentedAsyncPostgresSaver:
    """
    Get or create global InstrumentedAsyncPostgresSaver instance.

    LangGraph best practice (v0.2):
    - Single checkpointer instance with connection pool
    - No internal state kept by graph or checkpointer
    - Reuse connections across requests for performance

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
        - Setup is idempotent: safe to call multiple times
        - Connection string uses psycopg3 (not asyncpg) driver
        - Tables created: checkpoints, checkpoint_blobs, checkpoint_writes
        - Metrics exposed: checkpoint_save_duration_seconds, checkpoint_size_bytes
    """
    global _checkpointer

    if _checkpointer is None:
        logger.info("checkpointer_initializing", instrumented=True)

        # Convert asyncpg URL to psycopg3 URL
        # asyncpg format: postgresql+asyncpg://user:pass@host/db
        # psycopg3 format: postgresql://user:pass@host/db
        # Convert MultiHostUrl to string first
        database_url_str = str(settings.database_url)
        psycopg_url = database_url_str.replace("postgresql+asyncpg://", "postgresql://")

        # Create persistent connection for checkpointer
        # This connection stays open for the application lifetime
        global _connection
        _connection = await AsyncConnection.connect(
            psycopg_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,  # type: ignore[arg-type]  # psycopg3 row factory type complexity
        )

        # Create INSTRUMENTED checkpointer with persistent connection
        # The wrapper adds Prometheus metrics tracking without modifying LangGraph behavior
        serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
        _checkpointer = InstrumentedAsyncPostgresSaver(conn=_connection, serde=serde)  # type: ignore[arg-type]  # psycopg3 connection type

        # Setup checkpoint tables (idempotent)
        await _checkpointer.setup()

        logger.info(
            "checkpointer_initialized",
            tables_created=["checkpoints", "checkpoint_blobs", "checkpoint_writes"],
            instrumented=True,
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

    Closes connection pool gracefully to avoid hanging connections.

    Usage:
        Add to FastAPI lifespan shutdown hook:
        >>> @asynccontextmanager
        >>> async def lifespan(app: FastAPI):
        >>>     yield
        >>>     await cleanup_checkpointer()
    """
    global _checkpointer, _connection

    if _checkpointer is not None:
        logger.info("checkpointer_cleanup_started")

        # Close the persistent psycopg connection
        if _connection is not None:
            await _connection.close()
            _connection = None

        _checkpointer = None
        logger.info("checkpointer_cleanup_completed")


def reset_checkpointer() -> None:
    """
    Reset global checkpointer (for testing only).

    Clears global singleton without closing connection (connection will be
    closed when new checkpointer is created).

    WARNING: Only use in tests to force recreation of checkpointer.
    """
    global _checkpointer, _connection
    _checkpointer = None
    _connection = None
