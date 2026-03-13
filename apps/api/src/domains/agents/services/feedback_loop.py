"""
FeedbackLoopService - Learning from Recovery Patterns.

Architecture v3 - Intelligence, Autonomy, Relevance.

This service provides:
1. Recording of recovery attempts (success/failure)
2. Learning patterns from successful recoveries
3. Preemptive strategy suggestions based on learned patterns
4. Success rate tracking per strategy/domain

LEARNING APPROACH:
If BROADEN_SEARCH works for "jean", learn that:
- This pattern (short names, variable spelling) -> always broaden

Eventually, QueryIntelligence can:
- Anticipate likely fallbacks
- Automatically apply learned strategies
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from src.core.config.agents import V3FeedbackLoopConfig, get_v3_feedback_loop_config
from src.core.constants import (
    V3_FEEDBACK_LOOP_CONFIDENCE_THRESHOLD,
    V3_FEEDBACK_LOOP_MAX_RECORDS,
    V3_FEEDBACK_LOOP_MIN_SAMPLES,
)
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence

logger = get_logger(__name__)


class RecoveryOutcome(Enum):
    """Outcome of a recovery attempt."""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass
class RecoveryRecord:
    """Record of a recovery attempt."""

    timestamp: datetime
    original_query: str
    original_params: dict[str, Any]
    recovery_strategy: str
    recovered_params: dict[str, Any]
    outcome: RecoveryOutcome
    domain: str
    tool_name: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "original_query": self.original_query,
            "original_params": self.original_params,
            "recovery_strategy": self.recovery_strategy,
            "recovered_params": self.recovered_params,
            "outcome": self.outcome.value,
            "domain": self.domain,
            "tool_name": self.tool_name,
        }


@dataclass
class PatternMatch:
    """A learned pattern match."""

    pattern_key: str
    strategy: str
    success_count: int
    failure_count: int
    confidence: float  # success_count / total

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5


class FeedbackLoopService:
    """
    Learning from recovery successes.

    If BROADEN_SEARCH works for "jean", learn that:
    - This pattern (short names, variable spelling) -> always broaden

    Eventually, QueryIntelligence can:
    - Anticipate likely fallbacks
    - Automatically apply learned strategies
    """

    # Class-level defaults (for backwards compatibility with storage classes)
    MAX_RECORDS = V3_FEEDBACK_LOOP_MAX_RECORDS
    MIN_SAMPLES_FOR_SUGGESTION = V3_FEEDBACK_LOOP_MIN_SAMPLES
    CONFIDENCE_THRESHOLD = V3_FEEDBACK_LOOP_CONFIDENCE_THRESHOLD

    def __init__(
        self,
        storage: RecoveryStorage | None = None,
        config: V3FeedbackLoopConfig | None = None,
    ):
        # Load config from factory if not provided
        self._config = config or get_v3_feedback_loop_config()

        # Instance-level from config (for this instance's methods)
        self.max_records = self._config.max_records
        self.min_samples_for_suggestion = self._config.min_samples
        self.confidence_threshold = self._config.confidence_threshold

        self.storage = storage or InMemoryRecoveryStorage()
        self._pattern_cache: dict[str, list[tuple[str, RecoveryOutcome]]] = {}
        self._strategy_stats: dict[tuple[str, str], tuple[int, int]] = (
            {}
        )  # (strategy, domain) -> (success, failure)

    async def record_recovery(
        self,
        original_query: str,
        original_params: dict[str, Any],
        strategy: str,
        recovered_params: dict[str, Any],
        outcome: RecoveryOutcome,
        domain: str,
        tool_name: str,
    ) -> None:
        """
        Record a recovery attempt result.
        """
        record = RecoveryRecord(
            timestamp=datetime.now(UTC),
            original_query=original_query,
            original_params=original_params,
            recovery_strategy=strategy,
            recovered_params=recovered_params,
            outcome=outcome,
            domain=domain,
            tool_name=tool_name,
        )

        await self.storage.save(record)

        # Update pattern cache
        await self._learn_pattern(record)

        # Update strategy stats
        self._update_strategy_stats(strategy, domain, outcome)

        logger.debug(f"Recorded recovery: {strategy} for {domain}/{tool_name} -> {outcome.value}")

    async def _learn_pattern(self, record: RecoveryRecord) -> None:
        """
        Learn a pattern from a recovery record.

        Example:
        - Query: "jean" -> BROADEN_SEARCH success
        - Pattern learned: short names (< 5 chars) + contacts -> BROADEN_SEARCH
        """
        pattern_key = self._extract_pattern_key(record)

        if pattern_key not in self._pattern_cache:
            self._pattern_cache[pattern_key] = []

        self._pattern_cache[pattern_key].append((record.recovery_strategy, record.outcome))

        # Keep cache size reasonable
        if len(self._pattern_cache[pattern_key]) > 100:
            self._pattern_cache[pattern_key] = self._pattern_cache[pattern_key][-100:]

    def _extract_pattern_key(self, record: RecoveryRecord) -> str:
        """
        Extract a generic pattern key.

        Ex: "short_name:contacts:search" for "jean" -> search_contacts
        """
        query = record.original_query.strip()

        # Query length patterns
        if len(query) < 5:
            query_pattern = "very_short"
        elif len(query) < 10:
            query_pattern = "short"
        elif len(query.split()) == 1:
            query_pattern = "single_word"
        else:
            query_pattern = "multi_word"

        # Extract tool action
        tool_action = record.tool_name.split("_")[0] if "_" in record.tool_name else "unknown"

        return f"{query_pattern}:{record.domain}:{tool_action}"

    def _update_strategy_stats(
        self,
        strategy: str,
        domain: str,
        outcome: RecoveryOutcome,
    ) -> None:
        """Update success/failure stats for a strategy/domain pair."""
        key = (strategy, domain)
        current = self._strategy_stats.get(key, (0, 0))

        if outcome == RecoveryOutcome.SUCCESS:
            self._strategy_stats[key] = (current[0] + 1, current[1])
        else:
            self._strategy_stats[key] = (current[0], current[1] + 1)

    async def suggest_preemptive_strategies(
        self,
        intelligence: QueryIntelligence,
    ) -> list[str]:
        """
        Suggest strategies BEFORE failure, based on learning.

        If we learned that "short names + contacts" -> BROADEN_SEARCH works,
        suggest it directly in QueryIntelligence.anticipated_needs.
        """
        suggestions = []

        # Build potential pattern key
        query = intelligence.original_query.strip()

        # Determine query pattern
        if len(query) < 5:
            query_pattern = "very_short"
        elif len(query) < 10:
            query_pattern = "short"
        elif len(query.split()) == 1:
            query_pattern = "single_word"
        else:
            query_pattern = "multi_word"

        pattern_key = (
            f"{query_pattern}:{intelligence.primary_domain}:{intelligence.immediate_intent}"
        )

        # Look for learned patterns
        if pattern_key in self._pattern_cache:
            learned = self._pattern_cache[pattern_key]

            # Count successes per strategy
            success_strategies: list[str] = []
            for strategy, outcome in learned:
                if outcome == RecoveryOutcome.SUCCESS:
                    success_strategies.append(strategy)

            if success_strategies:
                # Suggest most common successful strategies
                most_common = Counter(success_strategies).most_common(2)

                for strategy, count in most_common:
                    if count >= self.min_samples_for_suggestion:
                        suggestions.append(strategy)

        # Also check strategy stats for high success rate
        for (strategy, domain), (success, failure) in self._strategy_stats.items():
            if domain != intelligence.primary_domain:
                continue

            total = success + failure
            if total >= self.min_samples_for_suggestion:
                rate = success / total
                if rate >= self.confidence_threshold and strategy not in suggestions:
                    suggestions.append(strategy)

        return suggestions[:3]  # Limit to top 3

    async def get_success_rate(
        self,
        strategy: str,
        domain: str,
    ) -> float:
        """
        Return success rate of a strategy for a domain.
        """
        key = (strategy, domain)
        stats = self._strategy_stats.get(key)

        if not stats:
            records = await self.storage.get_by_strategy_and_domain(strategy, domain)
            if not records:
                return 0.5  # Neutral if no data

            successes = sum(1 for r in records if r.outcome == RecoveryOutcome.SUCCESS)
            return successes / len(records)

        success, failure = stats
        total = success + failure
        return success / total if total > 0 else 0.5

    async def get_pattern_insights(
        self,
        domain: str | None = None,
    ) -> list[PatternMatch]:
        """
        Get insights about learned patterns.
        """
        insights = []

        for pattern_key, entries in self._pattern_cache.items():
            if domain and domain not in pattern_key:
                continue

            # Group by strategy
            strategy_counts: dict[str, tuple[int, int]] = {}
            for strategy, outcome in entries:
                current = strategy_counts.get(strategy, (0, 0))
                if outcome == RecoveryOutcome.SUCCESS:
                    strategy_counts[strategy] = (current[0] + 1, current[1])
                else:
                    strategy_counts[strategy] = (current[0], current[1] + 1)

            # Create pattern matches
            for strategy, (success, failure) in strategy_counts.items():
                total = success + failure
                if total >= self.min_samples_for_suggestion:
                    insights.append(
                        PatternMatch(
                            pattern_key=pattern_key,
                            strategy=strategy,
                            success_count=success,
                            failure_count=failure,
                            confidence=success / total,
                        )
                    )

        # Sort by confidence
        insights.sort(key=lambda x: x.confidence, reverse=True)

        return insights

    async def reset_learning(self) -> None:
        """Reset all learned patterns (for testing or retraining)."""
        self._pattern_cache.clear()
        self._strategy_stats.clear()
        await self.storage.clear()
        logger.info("Feedback loop learning reset")


class RecoveryStorage:
    """Base class for recovery storage."""

    async def save(self, record: RecoveryRecord) -> None:
        """Save a recovery record."""
        raise NotImplementedError

    async def get_by_strategy_and_domain(
        self,
        strategy: str,
        domain: str,
    ) -> list[RecoveryRecord]:
        """Get records by strategy and domain."""
        raise NotImplementedError

    async def get_all(self) -> list[RecoveryRecord]:
        """Get all records."""
        raise NotImplementedError

    async def clear(self) -> None:
        """Clear all records."""
        raise NotImplementedError


class InMemoryRecoveryStorage(RecoveryStorage):
    """In-memory storage for development."""

    def __init__(self) -> None:
        self.records: list[RecoveryRecord] = []

    async def save(self, record: RecoveryRecord) -> None:
        """Save a recovery record."""
        self.records.append(record)

        # Limit to MAX_RECORDS
        if len(self.records) > FeedbackLoopService.MAX_RECORDS:
            self.records = self.records[-FeedbackLoopService.MAX_RECORDS :]

    async def get_by_strategy_and_domain(
        self,
        strategy: str,
        domain: str,
    ) -> list[RecoveryRecord]:
        """Get records by strategy and domain."""
        return [r for r in self.records if r.recovery_strategy == strategy and r.domain == domain]

    async def get_all(self) -> list[RecoveryRecord]:
        """Get all records."""
        return self.records.copy()

    async def clear(self) -> None:
        """Clear all records."""
        self.records.clear()


class RedisRecoveryStorage(RecoveryStorage):
    """Redis-based storage for production.

    Uses Redis sorted sets for efficient:
    - Time-based retrieval (sorted by timestamp)
    - Automatic TTL-based cleanup
    - Multi-instance support (shared state)

    Keys structure:
    - feedback_loop:records - ZSET of all records (score = timestamp)
    - feedback_loop:strategy:{strategy}:{domain} - ZSET per strategy/domain

    TTL: 7 days (patterns older than 7 days are less relevant)
    """

    RECORDS_KEY = "feedback_loop:records"
    STRATEGY_KEY_PREFIX = "feedback_loop:strategy:"
    TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

    def __init__(self, redis_client: Any = None):
        self.redis = redis_client
        self._initialized = False

    async def _ensure_redis(self) -> Any:
        """Lazily get Redis client if not provided."""
        if self.redis is not None:
            return self.redis

        try:
            from src.infrastructure.cache.redis import get_redis_cache

            self.redis = await get_redis_cache()
            return self.redis
        except Exception as e:
            logger.warning(f"Redis not available for FeedbackLoop: {e}")
            return None

    async def save(self, record: RecoveryRecord) -> None:
        """Save a recovery record to Redis."""
        redis = await self._ensure_redis()
        if not redis:
            return

        try:
            import json

            # Serialize record
            record_json = json.dumps(record.to_dict())
            timestamp = record.timestamp.timestamp()

            # Add to main records set
            await redis.zadd(self.RECORDS_KEY, {record_json: timestamp})

            # Add to strategy-specific set for fast lookup
            strategy_key = f"{self.STRATEGY_KEY_PREFIX}{record.recovery_strategy}:{record.domain}"
            await redis.zadd(strategy_key, {record_json: timestamp})

            # Set TTL on keys (refresh on each write)
            await redis.expire(self.RECORDS_KEY, self.TTL_SECONDS)
            await redis.expire(strategy_key, self.TTL_SECONDS)

            # Trim to max records (keep most recent)
            max_records = FeedbackLoopService.MAX_RECORDS
            await redis.zremrangebyrank(self.RECORDS_KEY, 0, -max_records - 1)

            logger.debug(
                f"Saved recovery record to Redis: {record.recovery_strategy}/{record.domain}"
            )

        except Exception as e:
            logger.warning(f"Failed to save recovery record to Redis: {e}")

    async def get_by_strategy_and_domain(
        self,
        strategy: str,
        domain: str,
    ) -> list[RecoveryRecord]:
        """Get records from Redis by strategy and domain."""
        redis = await self._ensure_redis()
        if not redis:
            return []

        try:
            import json

            strategy_key = f"{self.STRATEGY_KEY_PREFIX}{strategy}:{domain}"
            records_json = await redis.zrange(strategy_key, 0, -1)

            records = []
            for record_json in records_json:
                try:
                    data = json.loads(record_json)
                    records.append(self._dict_to_record(data))
                except (json.JSONDecodeError, KeyError):
                    continue

            return records

        except Exception as e:
            logger.warning(f"Failed to get records from Redis: {e}")
            return []

    async def get_all(self) -> list[RecoveryRecord]:
        """Get all records from Redis."""
        redis = await self._ensure_redis()
        if not redis:
            return []

        try:
            import json

            records_json = await redis.zrange(self.RECORDS_KEY, 0, -1)

            records = []
            for record_json in records_json:
                try:
                    data = json.loads(record_json)
                    records.append(self._dict_to_record(data))
                except (json.JSONDecodeError, KeyError):
                    continue

            return records

        except Exception as e:
            logger.warning(f"Failed to get all records from Redis: {e}")
            return []

    async def clear(self) -> None:
        """Clear Redis records."""
        redis = await self._ensure_redis()
        if not redis:
            return

        try:
            # Delete main records key
            await redis.delete(self.RECORDS_KEY)

            # Delete all strategy keys (using pattern)
            pattern = f"{self.STRATEGY_KEY_PREFIX}*"
            async for key in redis.scan_iter(match=pattern):
                await redis.delete(key)

            logger.info("Cleared all FeedbackLoop records from Redis")

        except Exception as e:
            logger.warning(f"Failed to clear Redis records: {e}")

    def _dict_to_record(self, data: dict[str, Any]) -> RecoveryRecord:
        """Convert dict back to RecoveryRecord."""
        return RecoveryRecord(
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
            original_query=data["original_query"],
            original_params=data["original_params"],
            recovery_strategy=data["recovery_strategy"],
            recovered_params=data["recovered_params"],
            outcome=RecoveryOutcome(data["outcome"]),
            domain=data["domain"],
            tool_name=data["tool_name"],
        )


# Singleton
_service: FeedbackLoopService | None = None


def get_feedback_loop_service(
    use_redis: bool = True,
    config: V3FeedbackLoopConfig | None = None,
) -> FeedbackLoopService:
    """
    Get singleton FeedbackLoopService instance.

    Args:
        use_redis: If True, use Redis storage for persistence.
                   If False or Redis unavailable, use in-memory storage.
                   Default True for production use.
        config: Optional V3FeedbackLoopConfig. If not provided, loaded from env.

    Returns:
        FeedbackLoopService instance
    """
    global _service
    if _service is None:
        if use_redis:
            # Use Redis for production (lazy connection)
            storage = RedisRecoveryStorage()
        else:
            # Use in-memory for development/testing
            storage = InMemoryRecoveryStorage()  # type: ignore

        _service = FeedbackLoopService(
            storage=storage,
            config=config or get_v3_feedback_loop_config(),
        )
        logger.info(f"FeedbackLoopService initialized with {storage.__class__.__name__}")
    return _service


def reset_feedback_loop_service() -> None:
    """Reset service for testing."""
    global _service
    _service = None
