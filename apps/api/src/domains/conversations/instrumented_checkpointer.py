"""
Instrumented checkpointer wrapper for LangGraph state persistence with observability.

Wraps AsyncPostgresSaver to add Prometheus metrics tracking for checkpoint operations
without altering LangGraph's checkpoint semantics (state layout, SQL, serde).

This enables monitoring of:
- Checkpoint save/load duration (detect slow database writes/reads)
- Checkpoint payload sizes (detect conversation bloat)
- Checkpoint operation errors (database connectivity issues)
- Operation success/failure rates by type (save/load)
- Error categorization (db_connection/serialization/timeout/permission)

The wrapper is transparent to LangGraph - it passes through all method calls
while capturing metrics on the critical paths (aget_tuple, aput). Instrumenting
aget_tuple (not the aget convenience helper) matters: the LangGraph runtime
loads checkpoints exclusively through aget_tuple, and BaseCheckpointSaver.aget
itself delegates to aget_tuple, so both entry points are covered.

It additionally overrides the private `_cursor()` context manager to bypass the
instance-level lock when the saver runs on an `AsyncConnectionPool` (upstream
issue langchain-ai/langgraph#7259, fixed for the store but not the saver in
langgraph-checkpoint-postgres 3.1.0) — see ADR-111.

Phase 3.3 Metrics Added:
- checkpoint_operations_total{operation, status} - Counter for all operations
- checkpoint_errors_total{error_type, operation} - Counter for errors with categorization
"""

import asyncio
import pickle
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres import _ainternal
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncCursor
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    checkpoint_errors_total,
    checkpoint_load_duration_seconds,
    checkpoint_operations_total,
    checkpoint_save_duration_seconds,
    checkpoint_size_bytes,
)

logger = get_logger(__name__)


class InstrumentedAsyncPostgresSaver(AsyncPostgresSaver):
    """
    Instrumented wrapper around LangGraph's AsyncPostgresSaver.

    Tracks Prometheus metrics for checkpoint operations while preserving
    all AsyncPostgresSaver functionality and behavior.

    Metrics tracked (Phase 3.3):
    - checkpoint_save_duration_seconds: Time to save checkpoint (histogram)
    - checkpoint_load_duration_seconds: Time to load checkpoint (histogram)
    - checkpoint_size_bytes: Payload size in bytes (histogram)
    - checkpoint_operations_total: Operation count by type and status (counter)
    - checkpoint_errors_total: Error count by type and operation (counter)

    The wrapper intercepts these critical methods:
    - aput(): Checkpoint save (writes state to PostgreSQL)
    - aget_tuple(): Checkpoint load (reads state from PostgreSQL) — the method
      the LangGraph runtime actually calls; the inherited aget() convenience
      helper delegates here, so it is instrumented transitively

    It also overrides the private `_cursor()` context manager to make the saver
    pool-aware (bypass the instance-level lock when `conn` is an
    `AsyncConnectionPool`) — see `_cursor` docstring and ADR-111.

    All other methods (setup, alist, etc.) are passed through unchanged.

    Usage:
        >>> checkpointer = InstrumentedAsyncPostgresSaver(conn=connection)
        >>> await checkpointer.setup()  # Creates checkpoint tables
        >>> graph = build_graph(checkpointer=checkpointer)

    Notes:
        - node_name label extracted from config metadata if available
        - Size calculation uses pickle.dumps() to estimate serialized size
        - Errors are categorized (db_connection/serialization/timeout/permission)
        - All errors are logged AND re-raised (no silent failures)
    """

    @asynccontextmanager
    async def _cursor(self, *, pipeline: bool = False) -> AsyncIterator[AsyncCursor[DictRow]]:
        """Pool-aware override of `AsyncPostgresSaver._cursor` (upstream issue #7259).

        In langgraph-checkpoint-postgres 3.1.0 the parent implementation acquires
        the instance-level `self.lock` around EVERY database operation, even when
        `self.conn` is an `AsyncConnectionPool` — which serializes all concurrent
        checkpoint reads/writes of the worker on a single mutex and defeats the
        pool entirely. `AsyncPostgresStore._cursor` (same package, same release)
        already carries the fix: with a pool, each `_cursor()` call checks out its
        own connection and the pool never hands the same connection to two callers,
        so the shared lock is unnecessary. This override applies that exact
        reasoning to the saver, keeping the parent body verbatim otherwise.

        Safety argument (ADR-111): production already runs 4 uvicorn workers whose
        savers write concurrently to the same checkpoint tables with no
        cross-process lock — the instance lock therefore cannot be load-bearing
        for data consistency; it only guards single-connection exclusivity, which
        the pool checkout already guarantees.

        Behavior is bit-for-bit identical to the parent for single-connection
        (and pipeline) configurations: only the pooled case swaps the shared lock
        for a fresh no-op lock.

        REMOVE this override once upstream ships the fix for
        https://github.com/langchain-ai/langgraph/issues/7259 — the canary test
        `test_upstream_cursor_still_locks_pools` fails loudly when that happens.

        Args:
            pipeline: Whether to use pipeline mode for the DB operations inside
                the context manager (falls back to a transaction context manager
                when pipeline mode is not supported).

        Yields:
            An async cursor bound to a connection that is exclusively ours for
            the duration of the context.
        """
        is_pooled_conn = isinstance(self.conn, AsyncConnectionPool)
        lock = asyncio.Lock() if is_pooled_conn else self.lock
        async with lock, _ainternal.get_connection(self.conn) as conn:
            if self.pipe:
                # a connection in pipeline mode can be used concurrently
                # in multiple threads/coroutines, but only one cursor can be
                # used at a time
                try:
                    async with conn.cursor(binary=True, row_factory=dict_row) as cur:
                        yield cur
                finally:
                    if pipeline:
                        await self.pipe.sync()
            elif pipeline:
                # a connection not in pipeline mode can only be used by one
                # thread/coroutine at a time, so we acquire a lock
                if self.supports_pipeline:
                    async with (
                        conn.pipeline(),
                        conn.cursor(binary=True, row_factory=dict_row) as cur,
                    ):
                        yield cur
                else:
                    # Use connection's transaction context manager when pipeline mode not supported
                    async with (
                        conn.transaction(),
                        conn.cursor(binary=True, row_factory=dict_row) as cur,
                    ):
                        yield cur
            else:
                async with conn.cursor(binary=True, row_factory=dict_row) as cur:
                    yield cur

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """
        Save checkpoint to PostgreSQL with metrics instrumentation.

        Tracks:
        - Duration of checkpoint save operation
        - Size of checkpoint payload (serialized)

        Args:
            config: RunnableConfig with thread_id, checkpoint_id, etc.
            checkpoint: Checkpoint data to save (state dictionary)
            metadata: Checkpoint metadata (step, source, writes, etc.)
            new_versions: Version tracking for channels

        Returns:
            Updated RunnableConfig with new checkpoint_id

        Metrics:
            - checkpoint_save_duration_seconds{node_name}
            - checkpoint_size_bytes{node_name}
        """
        # Extract node_name from metadata for labeling
        node_name = metadata.get("source", "unknown") if metadata else "unknown"

        # Track save duration
        start_time = time.perf_counter()

        try:
            # Call parent implementation
            result = await super().aput(config, checkpoint, metadata, new_versions)

            # Calculate duration
            duration = time.perf_counter() - start_time
            checkpoint_save_duration_seconds.labels(node_name=node_name).observe(duration)

            # Track successful operation
            checkpoint_operations_total.labels(operation="save", status="success").inc()

            # Estimate checkpoint size (serialized payload)
            try:
                # Serialize checkpoint to estimate size
                serialized = pickle.dumps(checkpoint)
                size_bytes = len(serialized)
                checkpoint_size_bytes.labels(node_name=node_name).observe(size_bytes)

                logger.debug(
                    "checkpoint_saved",
                    node_name=node_name,
                    duration_ms=round(duration * 1000, 2),
                    size_bytes=size_bytes,
                    thread_id=config.get("configurable", {}).get("thread_id"),
                )
            except Exception as e:
                # Size calculation is best-effort, don't fail if it errors
                logger.warning(
                    "checkpoint_size_calculation_failed",
                    node_name=node_name,
                    error=str(e),
                )

            return result

        except Exception as e:
            # Log error but re-raise (don't swallow checkpoint failures)
            duration = time.perf_counter() - start_time

            # Track failed operation and categorize error
            checkpoint_operations_total.labels(operation="save", status="error").inc()

            # Categorize error type for better debugging
            error_type = "unknown"
            error_str = str(e)
            if "connection" in error_str.lower() or "connect" in error_str.lower():
                error_type = "db_connection"
            elif "timeout" in error_str.lower():
                error_type = "timeout"
            elif "pickle" in error_str.lower() or "serial" in error_str.lower():
                error_type = "serialization"
            elif "permission" in error_str.lower() or "denied" in error_str.lower():
                error_type = "permission"

            checkpoint_errors_total.labels(error_type=error_type, operation="save").inc()

            logger.error(
                "checkpoint_save_failed",
                node_name=node_name,
                duration_ms=round(duration * 1000, 2),
                error=str(e),
                error_type=error_type,
                thread_id=config.get("configurable", {}).get("thread_id"),
                exc_info=True,
            )
            raise

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """
        Load checkpoint tuple from PostgreSQL with metrics instrumentation.

        This overrides the method the LangGraph runtime uses for every
        checkpoint read (BaseCheckpointSaver.aget also delegates here), so the
        load metrics below cover all load paths. Tracks duration of the load
        operation; size is not tracked on load (already tracked during save).

        Args:
            config: RunnableConfig with thread_id, checkpoint_id to load

        Returns:
            CheckpointTuple with state data, or None if no checkpoint exists

        Metrics:
            - checkpoint_load_duration_seconds{node_name="checkpoint_load"}
        """
        start_time = time.perf_counter()

        try:
            # Call parent implementation
            result = await super().aget_tuple(config)

            # Calculate duration
            duration = time.perf_counter() - start_time

            # Track checkpoint load duration with generic node_name
            checkpoint_load_duration_seconds.labels(node_name="checkpoint_load").observe(duration)

            # Track successful operation
            checkpoint_operations_total.labels(operation="load", status="success").inc()

            logger.debug(
                "checkpoint_loaded",
                duration_ms=round(duration * 1000, 2),
                has_checkpoint=result is not None,
                thread_id=config.get("configurable", {}).get("thread_id"),
            )

            return result

        except Exception as e:
            duration = time.perf_counter() - start_time

            # Track failed operation and categorize error
            checkpoint_operations_total.labels(operation="load", status="error").inc()

            # Categorize error type for better debugging
            error_type = "unknown"
            error_str = str(e)
            if "connection" in error_str.lower() or "connect" in error_str.lower():
                error_type = "db_connection"
            elif "timeout" in error_str.lower():
                error_type = "timeout"
            elif "pickle" in error_str.lower() or "deserial" in error_str.lower():
                error_type = "deserialization"
            elif "permission" in error_str.lower() or "denied" in error_str.lower():
                error_type = "permission"

            checkpoint_errors_total.labels(error_type=error_type, operation="load").inc()

            logger.error(
                "checkpoint_load_failed",
                duration_ms=round(duration * 1000, 2),
                error=str(e),
                error_type=error_type,
                thread_id=config.get("configurable", {}).get("thread_id"),
                exc_info=True,
            )
            raise

    # All other methods (setup, alist, aget, etc.) are inherited unchanged from
    # AsyncPostgresSaver. The aget convenience helper delegates to aget_tuple,
    # so it is covered by the instrumentation above without an override.
