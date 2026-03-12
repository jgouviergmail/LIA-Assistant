"""
HITL Store Helper.

Centralized helper for storing and retrieving HITL interrupt data
with Redis schema versioning and fallback migration.

This module provides a clean abstraction over Redis for HITL-specific
data, with proper timestamp tracking and schema evolution support.
"""

import json
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as aioredis

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Current schema version for HITL interrupt data
SCHEMA_VERSION = 1


class HITLStore:
    """
    Helper class for storing and retrieving HITL interrupt data.

    Provides schema versioning and automatic migration from old formats.
    Tracks interrupt timestamps for response time metrics.

    Example:
        >>> store = HITLStore(redis_client, ttl_seconds=3600)
        >>> await store.save_interrupt(thread_id, {"action": "edit_contacts", ...})
        >>> data = await store.get_interrupt(thread_id)
        >>> await store.delete_interrupt(thread_id)
    """

    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: int) -> None:
        """
        Initialize HITLStore.

        Args:
            redis_client: Redis async client instance.
            ttl_seconds: TTL for interrupt data (recommended: 3600s).
        """
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds

    async def save_interrupt(self, thread_id: str, interrupt_data: dict[str, Any]) -> None:
        """
        Save HITL interrupt data with schema versioning and timestamp.

        Args:
            thread_id: Thread ID to store data for.
            interrupt_data: The interrupt payload (action, args, etc.).

        Example:
            >>> await store.save_interrupt("thread_123", {
            ...     "action_requests": [...],
            ...     "review_configs": None,
            ...     "run_id": "run_456"
            ... })
        """
        # Add schema version and interrupt timestamp
        versioned_data = {
            "schema_version": SCHEMA_VERSION,
            "interrupt_ts": datetime.now(UTC).isoformat(),
            "interrupt_data": interrupt_data,
        }

        key = f"hitl_pending:{thread_id}"
        await self.redis.set(key, json.dumps(versioned_data), ex=self.ttl_seconds)

        logger.info(
            "hitl_interrupt_saved",
            thread_id=thread_id,
            schema_version=SCHEMA_VERSION,
            ttl_seconds=self.ttl_seconds,
        )

    async def get_interrupt(self, thread_id: str) -> dict[str, Any] | None:
        """
        Retrieve HITL interrupt data with fallback migration.

        Automatically migrates old schema (plain dict) to new schema (versioned).

        Args:
            thread_id: Thread ID to retrieve data for.

        Returns:
            Versioned interrupt data dict, or None if not found.

        Example:
            >>> data = await store.get_interrupt("thread_123")
            >>> if data:
            ...     interrupt_ts = data["interrupt_ts"]
            ...     action = data["interrupt_data"]["action_requests"]
        """
        key = f"hitl_pending:{thread_id}"
        data_json = await self.redis.get(key)

        if data_json is None:
            return None

        # Parse JSON
        try:
            data = json.loads(data_json)
        except json.JSONDecodeError as e:
            logger.error(
                "hitl_interrupt_invalid_json",
                thread_id=thread_id,
                error=str(e),
            )
            return None

        # Handle old schema (plain dict without versioning)
        if "schema_version" not in data:
            logger.warning(
                "hitl_interrupt_old_schema",
                thread_id=thread_id,
                message="Migrating old schema to v1",
            )
            # Migrate: old schema was the raw interrupt_data
            migrated_data = {
                "schema_version": SCHEMA_VERSION,
                "interrupt_ts": datetime.now(UTC).isoformat(),  # Best effort
                "interrupt_data": data,
            }
            # Save migrated version back to Redis
            await self.redis.set(key, json.dumps(migrated_data), ex=self.ttl_seconds)
            return migrated_data

        return data

    async def delete_interrupt(self, thread_id: str) -> None:
        """
        Delete HITL interrupt data.

        Args:
            thread_id: Thread ID to delete data for.

        Example:
            >>> await store.delete_interrupt("thread_123")
        """
        key = f"hitl_pending:{thread_id}"
        await self.redis.delete(key)

        logger.info("hitl_interrupt_deleted", thread_id=thread_id)

    async def clear_interrupt(self, thread_id: str) -> None:
        """
        Clear HITL interrupt data (alias for delete_interrupt).

        Phase 3.3 Day 3: Added for semantic clarity when cleaning up
        after HITL completion (vs explicit deletion).

        Args:
            thread_id: Thread ID to clear data for.

        Example:
            >>> await store.clear_interrupt("thread_123")
        """
        await self.delete_interrupt(thread_id)

    async def has_interrupt(self, thread_id: str) -> bool:
        """
        Check if HITL interrupt data exists.

        Args:
            thread_id: Thread ID to check.

        Returns:
            True if interrupt data exists, False otherwise.
        """
        key = f"hitl_pending:{thread_id}"
        exists = await self.redis.exists(key)
        return exists > 0

    async def clear_if_invalid(self, thread_id: str) -> bool:
        """
        Clear pending HITL if it has no action_requests (stale/invalid state).

        FIX 2026-01-11: Prevents new messages from being incorrectly classified
        as HITL resumptions when the pending_hitl exists but has no content.

        Args:
            thread_id: Thread ID to validate and potentially clear.

        Returns:
            True if invalid pending_hitl was cleared, False if valid or not found.

        Example:
            >>> was_cleared = await store.clear_if_invalid("thread_123")
            >>> if was_cleared:
            ...     logger.info("Stale HITL state cleaned up")
        """
        from src.core.field_names import FIELD_ACTION_REQUESTS, FIELD_INTERRUPT_DATA

        pending_data = await self.get_interrupt(thread_id)

        if not pending_data:
            return False

        # Check if interrupt_data has action_requests
        interrupt_data = pending_data.get(FIELD_INTERRUPT_DATA, {})
        action_requests = interrupt_data.get(FIELD_ACTION_REQUESTS, [])

        if not action_requests:
            logger.warning(
                "hitl_invalid_state_cleared",
                thread_id=thread_id,
                reason="pending_hitl without action_requests",
                pending_keys=list(pending_data.keys()),
            )
            await self.clear_interrupt(thread_id)
            return True

        return False

    async def set_request_timestamp(self, thread_id: str, timestamp: float) -> None:
        """
        Store HITL request timestamp for response time metrics.

        Called when HITL interrupt is sent to user to track how long
        they take to respond (approve/reject/edit).

        Args:
            thread_id: Thread ID (conversation_id).
            timestamp: Unix timestamp (from time.time()).

        Example:
            >>> import time
            >>> await store.set_request_timestamp("thread_123", time.time())
        """
        key = f"hitl:request_ts:{thread_id}"
        # Store as string to avoid Redis serialization issues
        await self.redis.set(key, str(timestamp), ex=self.ttl_seconds)

        logger.debug(
            "hitl_request_timestamp_stored",
            thread_id=thread_id,
            timestamp=timestamp,
            ttl_seconds=self.ttl_seconds,
        )

    async def get_request_timestamp(self, thread_id: str) -> float | None:
        """
        Retrieve HITL request timestamp for response time calculation.

        Called when user responds to HITL interrupt to measure response time.

        Args:
            thread_id: Thread ID (conversation_id).

        Returns:
            Unix timestamp as float, or None if not found/expired.

        Example:
            >>> ts = await store.get_request_timestamp("thread_123")
            >>> if ts:
            ...     response_time = time.time() - ts
        """
        key = f"hitl:request_ts:{thread_id}"
        timestamp_str = await self.redis.get(key)

        if timestamp_str is None:
            return None

        try:
            return float(timestamp_str)
        except (ValueError, TypeError) as e:
            logger.error(
                "hitl_request_timestamp_invalid",
                thread_id=thread_id,
                timestamp_str=timestamp_str,
                error=str(e),
            )
            return None
