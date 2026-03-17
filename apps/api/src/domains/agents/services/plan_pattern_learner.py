"""
Plan Pattern Learner - Dynamic learning of planning patterns.

This service learns from validation successes and failures to guide the planner
toward validated patterns, reducing costly replanifications.

Architecture:
- Bayesian confidence with Beta(2,1) prior for fast ramp-up
- Fire-and-forget async for zero latency impact
- Shared Redis cross-users for global learning
- Strict anonymization (only tool sequence stored)

Usage:
    from src.domains.agents.services.plan_pattern_learner import (
        record_plan_success,
        record_plan_failure,
        get_learned_patterns_prompt,
        can_skip_validation,
    )

    # After validation
    if is_valid:
        record_plan_success(plan, query_intelligence)
    else:
        record_plan_failure(plan, query_intelligence)

    # In planner prompt
    learned = await get_learned_patterns_prompt(domains, is_mutation)

    # Bypass validation if high confidence
    if await can_skip_validation(plan):
        return  # Skip LLM validation

Created: 2026-01-12
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.core.constants import (
    PLAN_PATTERN_INTENT_MUTATION,
    PLAN_PATTERN_INTENT_READ,
    PLAN_PATTERN_REDIS_PREFIX,
)

if TYPE_CHECKING:
    from src.domains.agents.analysis.query_intelligence import QueryIntelligence
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# CONFIGURATION (loaded from settings at runtime)
# =============================================================================


class PatternConfig:
    """
    Configuration for Plan Pattern Learning.

    Loads from settings lazily to avoid circular imports.
    Values can be overridden via environment variables.
    """

    _instance: PatternConfig | None = None

    def __init__(self) -> None:
        self._loaded = False
        self._prior_alpha = 2
        self._prior_beta = 1
        self._min_obs_suggest = 3
        self._min_conf_suggest = 0.75
        self._min_obs_bypass = 10
        self._min_conf_bypass = 0.90
        self._max_suggestions = 3
        self._suggestion_timeout_ms = 5
        self._local_cache_ttl_s = 1.0
        self._redis_prefix = PLAN_PATTERN_REDIS_PREFIX
        self._redis_ttl_days = 30
        self._enabled = True
        self._training_enabled = True

    def _ensure_loaded(self) -> None:
        """Load from settings on first access."""
        if self._loaded:
            return
        try:
            from src.core.config import settings

            self._prior_alpha = settings.plan_pattern_prior_alpha
            self._prior_beta = settings.plan_pattern_prior_beta
            self._min_obs_suggest = settings.plan_pattern_min_obs_suggest
            self._min_conf_suggest = settings.plan_pattern_min_conf_suggest
            self._min_obs_bypass = settings.plan_pattern_min_obs_bypass
            self._min_conf_bypass = settings.plan_pattern_min_conf_bypass
            self._max_suggestions = settings.plan_pattern_max_suggestions
            self._suggestion_timeout_ms = settings.plan_pattern_suggestion_timeout_ms
            self._local_cache_ttl_s = settings.plan_pattern_local_cache_ttl_s
            self._redis_prefix = settings.plan_pattern_redis_prefix
            self._redis_ttl_days = settings.plan_pattern_redis_ttl_days
            # NOTE: Plan pattern learning is always enabled (_enabled = True by default)
            self._training_enabled = settings.plan_pattern_training_enabled
        except Exception:
            pass  # Use defaults if settings not available
        self._loaded = True

    @property
    def prior_alpha(self) -> int:
        self._ensure_loaded()
        return self._prior_alpha

    @property
    def prior_beta(self) -> int:
        self._ensure_loaded()
        return self._prior_beta

    @property
    def min_obs_suggest(self) -> int:
        self._ensure_loaded()
        return self._min_obs_suggest

    @property
    def min_conf_suggest(self) -> float:
        self._ensure_loaded()
        return self._min_conf_suggest

    @property
    def min_obs_bypass(self) -> int:
        self._ensure_loaded()
        return self._min_obs_bypass

    @property
    def min_conf_bypass(self) -> float:
        self._ensure_loaded()
        return self._min_conf_bypass

    @property
    def max_suggestions(self) -> int:
        self._ensure_loaded()
        return self._max_suggestions

    @property
    def suggestion_timeout_ms(self) -> int:
        self._ensure_loaded()
        return self._suggestion_timeout_ms

    @property
    def local_cache_ttl_s(self) -> float:
        self._ensure_loaded()
        return self._local_cache_ttl_s

    @property
    def redis_prefix(self) -> str:
        self._ensure_loaded()
        return self._redis_prefix

    @property
    def redis_ttl_seconds(self) -> int:
        self._ensure_loaded()
        return self._redis_ttl_days * 24 * 3600

    @property
    def enabled(self) -> bool:
        self._ensure_loaded()
        return self._enabled

    @property
    def training_enabled(self) -> bool:
        self._ensure_loaded()
        return self._training_enabled

    @classmethod
    def get(cls) -> PatternConfig:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = PatternConfig()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None


# Singleton instance
config = PatternConfig.get()


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True, slots=True)
class PatternStats:
    """
    Statistics for a planning pattern.

    Immutable to ensure data consistency.
    """

    key: str  # Pattern key (e.g., "get_contacts→send_email")
    successes: int  # Number of successful validations
    failures: int  # Number of failed validations
    domains: frozenset[str]  # Involved domains
    intent: str  # PLAN_PATTERN_INTENT_READ or PLAN_PATTERN_INTENT_MUTATION
    last_update: int  # Last update epoch timestamp

    @property
    def total(self) -> int:
        """Total number of observations."""
        return self.successes + self.failures

    @property
    def confidence(self) -> float:
        """
        Bayesian confidence with Beta(2,1) prior.

        Formula: (alpha + successes) / (alpha + beta + successes + failures)

        Examples:
        - 0s, 0f → 0.67 (prior)
        - 1s, 0f → 0.75
        - 3s, 0f → 0.83
        - 10s, 0f → 0.92
        - 3s, 1f → 0.80
        """
        alpha = config.prior_alpha + self.successes
        beta = config.prior_beta + self.failures
        return alpha / (alpha + beta)

    @property
    def is_suggerable(self) -> bool:
        """Check if the pattern can be suggested."""
        return self.total >= config.min_obs_suggest and self.confidence >= config.min_conf_suggest

    @property
    def can_bypass_validation(self) -> bool:
        """Check if the pattern has enough confidence to bypass validation."""
        return self.total >= config.min_obs_bypass and self.confidence >= config.min_conf_bypass

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "key": self.key,
            "successes": self.successes,
            "failures": self.failures,
            "total": self.total,
            "confidence": round(self.confidence, 3),
            "domains": sorted(self.domains),
            "intent": self.intent,
            "is_suggerable": self.is_suggerable,
            "can_bypass": self.can_bypass_validation,
            "last_update": self.last_update,
        }


# =============================================================================
# CORE SERVICE
# =============================================================================


class PlanPatternLearner:
    """
    Planning pattern learning service.

    GUARANTEES:
    - Emission: < 1ms (async fire-and-forget)
    - Suggestion: < 5ms (Redis + local cache)
    - Anonymization: Only the tool sequence is stored
    - Confidence ramp-up: 3 successes = suggestible, 10 = bypass

    THREAD-SAFETY:
    - All Redis operations are atomic (HINCRBY)
    - Local cache is thread-safe for reads (Python dict)
    """

    __slots__ = ("_redis", "_cache", "_cache_time")

    def __init__(self) -> None:
        self._redis: Any = None
        self._cache: dict[str, list[PatternStats]] = {}
        self._cache_time: float = 0

    # =========================================================================
    # KEY GENERATION (anonymized, deterministic, readable)
    # =========================================================================

    @staticmethod
    def make_pattern_key(plan: ExecutionPlan) -> str:
        """
        Generate a unique key based on the tool sequence.

        The key is:
        - Deterministic: same plan -> same key
        - Readable: easy to debug
        - Anonymous: no personal data

        Example: "get_contacts->send_email"
        Example FOR_EACH: "get_places->get_route[for_each]"
        """
        tools = []
        for step in plan.steps:
            tool = step.tool_name or "unknown"
            # Normalize name (remove _tool suffix for readability)
            if tool.endswith("_tool"):
                tool = tool[:-5]
            # Mark steps with for_each to match golden patterns
            if step.for_each is not None:
                tool = f"{tool}[for_each]"
            tools.append(tool)
        return "→".join(tools)

    @staticmethod
    def _redis_key(pattern_key: str) -> str:
        """Generate the full Redis key."""
        return f"{config.redis_prefix}:{pattern_key}"

    # =========================================================================
    # RECORDING (fire-and-forget async, < 1ms)
    # =========================================================================

    def record_success(
        self,
        plan: ExecutionPlan,
        query_intelligence: QueryIntelligence,
    ) -> None:
        """
        Record a validation success. Fire-and-forget.

        Args:
            plan: Successfully validated plan
            query_intelligence: Query intelligence
        """
        if not config.training_enabled:
            return
        asyncio.create_task(
            self._record(plan, query_intelligence, success=True),
            name="pattern_record_success",
        )

    def record_failure(
        self,
        plan: ExecutionPlan,
        query_intelligence: QueryIntelligence,
    ) -> None:
        """
        Record a validation failure. Fire-and-forget.

        Args:
            plan: Plan rejected by validation
            query_intelligence: Query intelligence
        """
        if not config.training_enabled:
            return
        asyncio.create_task(
            self._record(plan, query_intelligence, success=False),
            name="pattern_record_failure",
        )

    async def _record(
        self,
        plan: ExecutionPlan,
        qi: QueryIntelligence,
        success: bool,
    ) -> None:
        """Async implementation of recording."""
        redis = await self._ensure_redis()
        if not redis:
            return

        pattern_key = self.make_pattern_key(plan)
        redis_key = self._redis_key(pattern_key)

        try:
            # Prepare metadata (anonymized)
            domains = ",".join(sorted(qi.domains)) if qi.domains else ""
            intent = (
                PLAN_PATTERN_INTENT_MUTATION if qi.is_mutation_intent else PLAN_PATTERN_INTENT_READ
            )

            async with redis.pipeline() as pipe:
                # Increment appropriate counter (atomic)
                if success:
                    pipe.hincrby(redis_key, "s", 1)
                else:
                    pipe.hincrby(redis_key, "f", 1)

                # Metadata (set once, do not overwrite)
                pipe.hsetnx(redis_key, "d", domains)
                pipe.hsetnx(redis_key, "i", intent)

                # Last update timestamp
                pipe.hset(redis_key, "t", int(time.time()))

                # No TTL - patterns are permanent (golden patterns + learned)

                await pipe.execute()

            # Invalidate local cache
            self._cache.clear()
            self._cache_time = 0

            logger.info(
                "pattern_recorded",
                pattern=pattern_key,
                success=success,
                domains=domains,
                intent=intent,
            )

        except Exception as e:
            # Fire-and-forget: log and continue (WARNING for visibility)
            logger.warning(
                "pattern_recording_failed",
                error=str(e),
                pattern=pattern_key,
            )

    # =========================================================================
    # SUGGESTIONS (< 5ms with cache)
    # =========================================================================

    async def get_suggestions(
        self,
        domains: list[str],
        is_mutation: bool,
    ) -> list[PatternStats]:
        """
        Return suggested patterns for this context.

        Args:
            domains: Query domains
            is_mutation: True if mutation intent

        Returns:
            List of PatternStats sorted by descending confidence

        Note:
            Strict 5ms timeout to avoid latency impact.
            Returns empty list on timeout or error.
        """
        if not config.enabled:
            return []

        # Local cache (avoids Redis for repetitive requests)
        cache_key = f"{','.join(sorted(domains))}:{is_mutation}"
        now = time.time()

        if now - self._cache_time < config.local_cache_ttl_s:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            patterns = await asyncio.wait_for(
                self._fetch_suggestions(domains, is_mutation),
                timeout=config.suggestion_timeout_ms / 1000,
            )

            # Store in cache
            self._cache[cache_key] = patterns
            self._cache_time = now

            return patterns

        except TimeoutError:
            logger.debug("pattern_suggestion_timeout")
            return []
        except Exception as e:
            logger.debug(
                "pattern_suggestion_failed",
                error=str(e),
            )
            return []

    async def _fetch_suggestions(
        self,
        domains: list[str],
        is_mutation: bool,
    ) -> list[PatternStats]:
        """Fetch suggestions from Redis."""
        redis = await self._ensure_redis()
        if not redis:
            logger.debug("_fetch_suggestions_no_redis")
            return []

        intent = PLAN_PATTERN_INTENT_MUTATION if is_mutation else PLAN_PATTERN_INTENT_READ
        domain_set = set(domains)

        logger.debug(
            "_fetch_suggestions_start",
            domains=sorted(domains),
            domain_set=sorted(domain_set),
            is_mutation=is_mutation,
            intent=intent,
            redis_prefix=config.redis_prefix,
        )

        # Scan all patterns (few in number, < 100)
        patterns: list[PatternStats] = []
        scanned_count = 0

        async for key in redis.scan_iter(f"{config.redis_prefix}:*"):
            scanned_count += 1
            try:
                data = await redis.hgetall(key)
                if not data:
                    continue

                # Filter by intent
                pattern_intent = data.get("i", PLAN_PATTERN_INTENT_READ)
                if pattern_intent != intent:
                    continue

                # Filter by domains: EXACT MATCH only
                # Only patterns with exactly the same domains are relevant
                # Example: query [contacts, emails] -> only patterns [contacts, emails]
                pattern_domains_str = data.get("d", "")
                pattern_domains = (
                    set(pattern_domains_str.split(",")) if pattern_domains_str else set()
                )
                if pattern_domains != domain_set:
                    continue

                # Build PatternStats
                pattern_key = key.replace(f"{config.redis_prefix}:", "")
                stats = PatternStats(
                    key=pattern_key,
                    successes=int(data.get("s", 0)),
                    failures=int(data.get("f", 0)),
                    domains=frozenset(pattern_domains),
                    intent=pattern_intent,
                    last_update=int(data.get("t", 0)),
                )

                # Only keep suggestible patterns
                if stats.is_suggerable:
                    patterns.append(stats)

            except Exception:
                continue

        # Sort by descending confidence
        patterns.sort(key=lambda p: p.confidence, reverse=True)

        logger.debug(
            "_fetch_suggestions_complete",
            scanned_count=scanned_count,
            matched_count=len(patterns),
            patterns=[p.key for p in patterns[:5]],
        )

        return patterns[: config.max_suggestions]

    async def should_bypass_validation(
        self,
        plan: ExecutionPlan,
        query_intelligence: QueryIntelligence | None = None,
    ) -> bool:
        """
        Check if this pattern has enough confidence to bypass validation.

        SECURITY FIX 2026-01-14: Now verifies that the stored pattern's domains
        and intent match the current query. This prevents a read-only pattern
        from bypassing validation for a mutation query.

        Args:
            plan: Plan to verify
            query_intelligence: QueryIntelligence for domain/intent verification

        Returns:
            True if the pattern has confidence >= 90% with >= 10 observations
            AND domains/intent match the current query
        """
        if not config.enabled:
            return False

        redis = await self._ensure_redis()
        if not redis:
            return False

        pattern_key = self.make_pattern_key(plan)
        redis_key = self._redis_key(pattern_key)

        try:
            data = await asyncio.wait_for(
                redis.hgetall(redis_key),
                timeout=config.suggestion_timeout_ms / 1000,
            )

            if not data:
                return False

            # Extract stored pattern metadata
            pattern_domains_str = data.get("d", "")
            pattern_domains = (
                frozenset(pattern_domains_str.split(",")) if pattern_domains_str else frozenset()
            )
            pattern_intent = data.get("i", PLAN_PATTERN_INTENT_READ)

            stats = PatternStats(
                key=pattern_key,
                successes=int(data.get("s", 0)),
                failures=int(data.get("f", 0)),
                domains=pattern_domains,
                intent=pattern_intent,
                last_update=int(data.get("t", 0)),
            )

            # Check confidence threshold first (fast path)
            if not stats.can_bypass_validation:
                return False

            # =====================================================================
            # SECURITY FIX: Verify domains and intent match current query
            # =====================================================================
            # Without this check, a pattern like "get_contacts" with intent=read
            # could bypass validation for a mutation query like "send email to X"
            # where the planner incorrectly generated only 1 step.
            # =====================================================================
            if query_intelligence:
                # Verify intent matches
                current_intent = (
                    PLAN_PATTERN_INTENT_MUTATION
                    if query_intelligence.is_mutation_intent
                    else PLAN_PATTERN_INTENT_READ
                )
                if pattern_intent != current_intent:
                    logger.info(
                        "pattern_bypass_rejected_intent_mismatch",
                        pattern=pattern_key,
                        pattern_intent=pattern_intent,
                        query_intent=current_intent,
                    )
                    return False

                # Verify domains match (exact match required)
                current_domains = frozenset(query_intelligence.domains or [])
                if pattern_domains != current_domains:
                    logger.info(
                        "pattern_bypass_rejected_domain_mismatch",
                        pattern=pattern_key,
                        pattern_domains=sorted(pattern_domains),
                        query_domains=sorted(current_domains),
                    )
                    return False

            logger.info(
                "pattern_bypass_validation",
                pattern=pattern_key,
                confidence=round(stats.confidence, 3),
                total=stats.total,
                domains=sorted(pattern_domains),
                intent=pattern_intent,
            )

            return True

        except (TimeoutError, Exception):
            return False

    # =========================================================================
    # PROMPT INJECTION
    # =========================================================================

    async def get_prompt_section(
        self,
        domains: list[str],
        is_mutation: bool,
    ) -> str:
        """
        Generate the section to inject into the planner prompt.

        Args:
            domains: Query domains
            is_mutation: True if mutation intent

        Returns:
            Formatted section or empty string if no suggestions
        """
        logger.debug(
            "get_prompt_section_called",
            domains=domains,
            is_mutation=is_mutation,
        )

        suggestions = await self.get_suggestions(domains, is_mutation)

        if not suggestions:
            logger.debug(
                "get_prompt_section_no_suggestions",
                domains=domains,
                is_mutation=is_mutation,
            )
            return ""

        logger.info(
            "get_prompt_section_suggestions_found",
            domains=domains,
            is_mutation=is_mutation,
            suggestion_count=len(suggestions),
            suggestions=[s.key for s in suggestions],
        )

        lines = [
            "VALIDATED PATTERNS (high success rate - PREFER these structures):",
        ]

        for i, p in enumerate(suggestions, 1):
            # Readable format: get_contacts → send_email
            tools = p.key.replace("→", " → ")
            conf = int(p.confidence * 100)
            lines.append(f"  {i}. {tools} ({conf}% success, {p.total} samples)")

        lines.append("")

        return "\n".join(lines)

    # =========================================================================
    # ADMIN / MAINTENANCE
    # =========================================================================

    async def list_all_patterns(self) -> list[PatternStats]:
        """
        List all registered patterns.

        Returns:
            Complete list of patterns sorted by confidence
        """
        redis = await self._ensure_redis()
        if not redis:
            return []

        patterns: list[PatternStats] = []

        try:
            async for key in redis.scan_iter(f"{config.redis_prefix}:*"):
                data = await redis.hgetall(key)
                if not data:
                    continue

                pattern_key = key.replace(f"{config.redis_prefix}:", "")
                domains_str = data.get("d", "")

                stats = PatternStats(
                    key=pattern_key,
                    successes=int(data.get("s", 0)),
                    failures=int(data.get("f", 0)),
                    domains=frozenset(domains_str.split(",")) if domains_str else frozenset(),
                    intent=data.get("i", PLAN_PATTERN_INTENT_READ),
                    last_update=int(data.get("t", 0)),
                )
                patterns.append(stats)

            # Sort by descending confidence
            patterns.sort(key=lambda p: p.confidence, reverse=True)

        except Exception as e:
            logger.error(
                "pattern_list_failed",
                error=str(e),
            )

        return patterns

    async def get_pattern(self, pattern_key: str) -> PatternStats | None:
        """
        Get stats for a specific pattern.

        Args:
            pattern_key: Pattern key (e.g., "get_contacts->send_email")

        Returns:
            PatternStats or None if not found
        """
        redis = await self._ensure_redis()
        if not redis:
            return None

        redis_key = self._redis_key(pattern_key)

        try:
            data = await redis.hgetall(redis_key)
            if not data:
                return None

            domains_str = data.get("d", "")

            return PatternStats(
                key=pattern_key,
                successes=int(data.get("s", 0)),
                failures=int(data.get("f", 0)),
                domains=frozenset(domains_str.split(",")) if domains_str else frozenset(),
                intent=data.get("i", PLAN_PATTERN_INTENT_READ),
                last_update=int(data.get("t", 0)),
            )

        except Exception as e:
            logger.error(
                "pattern_get_failed",
                error=str(e),
                pattern_key=pattern_key,
            )
            return None

    async def delete_pattern(self, pattern_key: str) -> bool:
        """
        Delete a pattern.

        Args:
            pattern_key: Key of the pattern to delete

        Returns:
            True if deleted, False otherwise
        """
        redis = await self._ensure_redis()
        if not redis:
            return False

        redis_key = self._redis_key(pattern_key)

        try:
            result = await redis.delete(redis_key)

            if result:
                logger.info("pattern_deleted", pattern=pattern_key)
                # Invalidate cache
                self._cache.clear()
                self._cache_time = 0

            return bool(result)

        except Exception as e:
            logger.error(
                "pattern_delete_failed",
                error=str(e),
                pattern_key=pattern_key,
            )
            return False

    async def delete_all_patterns(self) -> int:
        """
        Delete all patterns (full reset).

        Returns:
            Number of patterns deleted
        """
        redis = await self._ensure_redis()
        if not redis:
            return 0

        count = 0

        try:
            async for key in redis.scan_iter(f"{config.redis_prefix}:*"):
                await redis.delete(key)
                count += 1

            logger.info("all_patterns_deleted", count=count)

            # Invalidate cache
            self._cache.clear()
            self._cache_time = 0

        except Exception as e:
            logger.error(
                "pattern_delete_all_failed",
                error=str(e),
            )

        return count

    async def seed_pattern(
        self,
        pattern_key: str,
        domains: list[str],
        intent: str,
        successes: int = 5,
        failures: int = 0,
    ) -> bool:
        """
        Create a pattern with initial values (seeding).

        Useful for bootstrapping with known patterns.

        Args:
            pattern_key: Pattern key (e.g., "get_contacts->send_email")
            domains: Involved domains
            intent: PLAN_PATTERN_INTENT_READ or PLAN_PATTERN_INTENT_MUTATION
            successes: Initial number of successes
            failures: Initial number of failures

        Returns:
            True if created, False otherwise
        """
        redis = await self._ensure_redis()
        if not redis:
            return False

        redis_key = self._redis_key(pattern_key)

        try:
            await redis.hset(
                redis_key,
                mapping={
                    "s": successes,
                    "f": failures,
                    "d": ",".join(sorted(domains)),
                    "i": intent,
                    "t": int(time.time()),
                },
            )
            # No TTL - patterns are permanent

            logger.info(
                "pattern_seeded",
                pattern=pattern_key,
                successes=successes,
                failures=failures,
            )

            # Invalidate cache
            self._cache.clear()
            self._cache_time = 0

            return True

        except Exception as e:
            logger.error(
                "pattern_seed_failed",
                error=str(e),
                pattern_key=pattern_key,
            )
            return False

    async def get_stats_summary(self) -> dict[str, Any]:
        """
        Return a summary of global statistics.

        Returns:
            Dict with aggregated metrics
        """
        patterns = await self.list_all_patterns()

        if not patterns:
            return {
                "total_patterns": 0,
                "suggerable_patterns": 0,
                "bypassable_patterns": 0,
                "total_observations": 0,
                "total_successes": 0,
                "total_failures": 0,
                "global_success_rate": 0.0,
                "avg_confidence": 0.0,
            }

        suggerable = [p for p in patterns if p.is_suggerable]
        bypassable = [p for p in patterns if p.can_bypass_validation]

        total_obs = sum(p.total for p in patterns)
        total_success = sum(p.successes for p in patterns)
        total_failure = sum(p.failures for p in patterns)

        return {
            "total_patterns": len(patterns),
            "suggerable_patterns": len(suggerable),
            "bypassable_patterns": len(bypassable),
            "total_observations": total_obs,
            "total_successes": total_success,
            "total_failures": total_failure,
            "global_success_rate": round(total_success / total_obs, 3) if total_obs > 0 else 0.0,
            "avg_confidence": round(sum(p.confidence for p in patterns) / len(patterns), 3),
        }

    # =========================================================================
    # REDIS CONNECTION
    # =========================================================================

    async def _ensure_redis(self) -> Any:
        """Lazy-load Redis client."""
        if self._redis is not None:
            return self._redis

        try:
            from src.infrastructure.cache.redis import get_redis_cache

            self._redis = await get_redis_cache()
            return self._redis
        except Exception as e:
            logger.debug(
                "pattern_redis_unavailable",
                error=str(e),
            )
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_learner: PlanPatternLearner | None = None


def get_pattern_learner() -> PlanPatternLearner:
    """
    Return the PlanPatternLearner singleton.

    Creates the instance on first call. Config is read from PatternConfig singleton.
    """
    global _learner
    if _learner is None:
        _learner = PlanPatternLearner()
        logger.info(
            "plan_pattern_learner_initialized",
            enabled=config.enabled,
            training_enabled=config.training_enabled,
        )

    return _learner


def reset_pattern_learner() -> None:
    """Reset the singleton (for tests)."""
    global _learner
    _learner = None


# =============================================================================
# CONVENIENCE FUNCTIONS (simplified public API)
# =============================================================================


def record_plan_success(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """
    Record a validation success.

    Fire-and-forget: returns immediately, recording is async.
    """
    get_pattern_learner().record_success(plan, qi)


def record_plan_failure(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """
    Record a validation failure.

    Fire-and-forget: returns immediately, recording is async.
    """
    get_pattern_learner().record_failure(plan, qi)


async def get_learned_patterns_prompt(domains: list[str], is_mutation: bool) -> str:
    """
    Return the learned patterns section to inject into the prompt.

    Args:
        domains: Query domains
        is_mutation: True if mutation intent

    Returns:
        Formatted section or empty string
    """
    return await get_pattern_learner().get_prompt_section(domains, is_mutation)


async def can_skip_validation(
    plan: ExecutionPlan,
    query_intelligence: QueryIntelligence | None = None,
) -> bool:
    """
    Check if the pattern has enough confidence to skip LLM validation.

    SECURITY FIX 2026-01-14: Now requires query_intelligence to verify that
    the stored pattern's domains and intent match the current query.

    Args:
        plan: Plan to verify
        query_intelligence: QueryIntelligence for domain/intent verification.
                           If None, only confidence is checked (legacy behavior).

    Returns:
        True si confidence >= 90% avec >= 10 observations AND domains/intent match
    """
    return await get_pattern_learner().should_bypass_validation(plan, query_intelligence)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Service
    "PlanPatternLearner",
    "get_pattern_learner",
    "reset_pattern_learner",
    # Data
    "PatternStats",
    # Convenience functions
    "record_plan_success",
    "record_plan_failure",
    "get_learned_patterns_prompt",
    "can_skip_validation",
    # Configuration
    "config",
    "PatternConfig",
]
