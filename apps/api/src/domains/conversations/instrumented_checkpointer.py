"""
Instrumented checkpointer wrapper for LangGraph state persistence with observability.

Wraps AsyncPostgresSaver to add Prometheus metrics tracking for checkpoint operations
without modifying LangGraph's internal checkpoint mechanism.

This enables monitoring of:
- Checkpoint save/load duration (detect slow database writes/reads)
- Checkpoint payload sizes (detect conversation bloat)
- Checkpoint operation errors (database connectivity issues)
- Operation success/failure rates by type (save/load)
- Error categorization (db_connection/serialization/timeout/permission)

The wrapper is transparent to LangGraph - it passes through all method calls
while capturing metrics on the critical paths (aget, aput, alist).

Phase 3.3 Metrics Added:
- checkpoint_operations_total{operation, status} - Counter for all operations
- checkpoint_errors_total{error_type, operation} - Counter for errors with categorization
"""

import pickle
import time
from typing import cast as typing_cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

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
    - aget(): Checkpoint load (reads state from PostgreSQL)
    - alist(): Checkpoint list (queries checkpoint history)

    All other methods (setup, atuple, etc.) are passed through unchanged.

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

    async def aget(self, config: RunnableConfig) -> CheckpointTuple | None:  # type: ignore[override]
        """
        Load checkpoint from PostgreSQL with metrics instrumentation.

        Tracks duration of checkpoint load operation. Size is not tracked on load
        (already tracked during save).

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
            result = await super().aget(config)

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

            return typing_cast(CheckpointTuple | None, result)

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

    # All other methods (setup, atuple, alist, etc.) are inherited unchanged
    # from AsyncPostgresSaver. No need to override if we don't need metrics for them.
