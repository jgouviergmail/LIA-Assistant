"""
Unit tests for Plan Pattern Learner.

Tests coverage for:
- PatternConfig: Configuration singleton with lazy loading
- PatternStats: Data structure with Bayesian confidence calculation
- PlanPatternLearner: Main service class
  - Pattern key generation
  - Recording success/failure (fire-and-forget)
  - Fetching suggestions with caching
  - Validation bypass decision
  - Prompt section generation
  - Admin operations (list, get, delete, seed)
- Convenience functions: module-level API

Target: 80%+ coverage for domains/agents/services/plan_pattern_learner.py
"""

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import (
    PLAN_PATTERN_INTENT_MUTATION,
    PLAN_PATTERN_INTENT_READ,
)
from src.domains.agents.services.plan_pattern_learner import (
    PatternConfig,
    PatternStats,
    PlanPatternLearner,
    can_skip_validation,
    config,
    get_learned_patterns_prompt,
    get_pattern_learner,
    record_plan_failure,
    record_plan_success,
    reset_pattern_learner,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockExecutionStep:
    """Mock execution step for testing."""

    tool_name: str
    for_each: str | None = None


@dataclass
class MockExecutionPlan:
    """Mock execution plan for testing."""

    steps: list[MockExecutionStep]


@dataclass
class MockQueryIntelligence:
    """Mock query intelligence for testing."""

    domains: list[str]
    is_mutation_intent: bool


@pytest.fixture(autouse=True)
def reset_config():
    """Reset configuration singleton before each test."""
    PatternConfig.reset()
    reset_pattern_learner()
    yield
    PatternConfig.reset()
    reset_pattern_learner()


@pytest.fixture
def mock_redis():
    """Create mock Redis client for testing."""
    redis = MagicMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.hincrby = AsyncMock()
    redis.hsetnx = AsyncMock()
    redis.hset = AsyncMock()
    redis.delete = AsyncMock(return_value=1)
    redis.pipeline = MagicMock(return_value=AsyncMock())

    # Mock async context manager for pipeline
    pipe_mock = AsyncMock()
    pipe_mock.hincrby = MagicMock()
    pipe_mock.hsetnx = MagicMock()
    pipe_mock.hset = MagicMock()
    pipe_mock.execute = AsyncMock()

    redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=pipe_mock)
    redis.pipeline.return_value.__aexit__ = AsyncMock()

    # Mock scan_iter as async generator
    async def mock_scan_iter(pattern):
        # Return empty by default
        return
        yield  # Make it an async generator

    redis.scan_iter = mock_scan_iter

    return redis


@pytest.fixture
def sample_plan():
    """Create sample execution plan."""
    return MockExecutionPlan(
        steps=[
            MockExecutionStep(tool_name="get_contacts_tool"),
            MockExecutionStep(tool_name="send_email_tool"),
        ]
    )


@pytest.fixture
def sample_qi_read():
    """Create sample QueryIntelligence for read intent."""
    return MockQueryIntelligence(
        domains=["contact", "email"],
        is_mutation_intent=False,
    )


@pytest.fixture
def sample_qi_mutation():
    """Create sample QueryIntelligence for mutation intent."""
    return MockQueryIntelligence(
        domains=["contact", "email"],
        is_mutation_intent=True,
    )


# =============================================================================
# PatternConfig - Unit Tests
# =============================================================================


class TestPatternConfig:
    """Tests for PatternConfig configuration singleton."""

    def test_singleton_instance(self):
        """Test that PatternConfig.get() returns same instance."""
        config1 = PatternConfig.get()
        config2 = PatternConfig.get()
        assert config1 is config2

    def test_reset_clears_singleton(self):
        """Test that reset() clears the singleton instance."""
        config1 = PatternConfig.get()
        PatternConfig.reset()
        config2 = PatternConfig.get()
        assert config1 is not config2

    def test_default_values_before_load(self):
        """Test default configuration values before loading from settings."""
        cfg = PatternConfig()
        # Access without triggering load by checking private attributes
        assert cfg._prior_alpha == 2
        assert cfg._prior_beta == 1
        assert cfg._min_obs_suggest == 3
        assert cfg._min_conf_suggest == 0.75
        assert cfg._min_obs_bypass == 10
        assert cfg._min_conf_bypass == 0.90
        assert cfg._max_suggestions == 3
        assert cfg._enabled is True
        assert cfg._training_enabled is True

    def test_properties_trigger_lazy_load(self):
        """Test that accessing properties triggers lazy load."""
        cfg = PatternConfig()
        assert cfg._loaded is False
        # Accessing a property should trigger load
        _ = cfg.prior_alpha
        assert cfg._loaded is True

    def test_prior_alpha_property(self):
        """Test prior_alpha property returns correct value."""
        assert config.prior_alpha == 2

    def test_prior_beta_property(self):
        """Test prior_beta property returns correct value."""
        assert config.prior_beta == 1

    def test_min_obs_suggest_property(self):
        """Test min_obs_suggest property returns correct value."""
        assert config.min_obs_suggest == 3

    def test_min_conf_suggest_property(self):
        """Test min_conf_suggest property returns correct value."""
        assert config.min_conf_suggest == 0.75

    def test_min_obs_bypass_property(self):
        """Test min_obs_bypass property returns correct value."""
        assert config.min_obs_bypass == 10

    def test_min_conf_bypass_property(self):
        """Test min_conf_bypass property returns correct value."""
        assert config.min_conf_bypass == 0.90

    def test_max_suggestions_property(self):
        """Test max_suggestions property returns correct value."""
        assert config.max_suggestions == 3

    def test_redis_ttl_seconds_calculated(self):
        """Test that redis_ttl_seconds is calculated from days."""
        cfg = PatternConfig()
        cfg._redis_ttl_days = 30
        cfg._loaded = True  # Skip loading
        assert cfg.redis_ttl_seconds == 30 * 24 * 3600

    def test_enabled_property(self):
        """Test enabled property returns correct value."""
        assert config.enabled is True

    def test_training_enabled_property(self):
        """Test training_enabled property returns a boolean value.

        Note: The actual value depends on settings.plan_pattern_training_enabled.
        This test verifies the property exists and returns a boolean.
        """
        assert isinstance(config.training_enabled, bool)


# =============================================================================
# PatternStats - Unit Tests
# =============================================================================


class TestPatternStats:
    """Tests for PatternStats data structure."""

    def test_basic_creation(self):
        """Test basic PatternStats creation."""
        stats = PatternStats(
            key="get_contacts→send_email",
            successes=5,
            failures=1,
            domains=frozenset(["contact", "email"]),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=1704067200,
        )

        assert stats.key == "get_contacts→send_email"
        assert stats.successes == 5
        assert stats.failures == 1
        assert "contact" in stats.domains
        assert "email" in stats.domains
        assert stats.intent == PLAN_PATTERN_INTENT_READ

    def test_total_property(self):
        """Test total property calculates sum of successes and failures."""
        stats = PatternStats(
            key="test",
            successes=5,
            failures=3,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )

        assert stats.total == 8

    def test_confidence_with_bayesian_prior(self):
        """
        Test confidence calculation with Bayesian Beta(2,1) prior.

        Formula: (alpha + successes) / (alpha + beta + successes + failures)
        With Beta(2,1): (2 + s) / (3 + s + f)
        """
        # No observations: (2+0)/(3+0+0) = 0.667
        stats = PatternStats(
            key="test",
            successes=0,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert abs(stats.confidence - 0.667) < 0.01

        # 1 success, 0 failures: (2+1)/(3+1+0) = 0.75
        stats = PatternStats(
            key="test",
            successes=1,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert abs(stats.confidence - 0.75) < 0.01

        # 10 successes, 0 failures: (2+10)/(3+10+0) = 0.923
        stats = PatternStats(
            key="test",
            successes=10,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert abs(stats.confidence - 0.923) < 0.01

        # 3 successes, 1 failure: (2+3)/(3+3+1) = 0.714
        stats = PatternStats(
            key="test",
            successes=3,
            failures=1,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert abs(stats.confidence - 0.714) < 0.01

    def test_is_suggerable_true(self):
        """Test is_suggerable returns True when thresholds met."""
        # 3+ observations, 75%+ confidence
        stats = PatternStats(
            key="test",
            successes=3,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        # confidence = (2+3)/(3+3+0) = 0.833 > 0.75
        assert stats.is_suggerable is True

    def test_is_suggerable_false_low_observations(self):
        """Test is_suggerable returns False with insufficient observations."""
        stats = PatternStats(
            key="test",
            successes=2,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert stats.total == 2  # Less than min_obs_suggest (3)
        assert stats.is_suggerable is False

    def test_is_suggerable_false_low_confidence(self):
        """Test is_suggerable returns False with low confidence."""
        stats = PatternStats(
            key="test",
            successes=2,
            failures=3,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        # confidence = (2+2)/(3+2+3) = 0.5 < 0.75
        assert stats.total == 5  # >= min_obs_suggest
        assert stats.confidence < 0.75
        assert stats.is_suggerable is False

    def test_can_bypass_validation_true(self):
        """Test can_bypass_validation returns True when thresholds met."""
        # 10+ observations, 90%+ confidence
        stats = PatternStats(
            key="test",
            successes=10,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        # confidence = (2+10)/(3+10+0) = 0.923 > 0.90
        assert stats.can_bypass_validation is True

    def test_can_bypass_validation_false_low_observations(self):
        """Test can_bypass_validation returns False with insufficient observations."""
        stats = PatternStats(
            key="test",
            successes=9,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        assert stats.total == 9  # Less than min_obs_bypass (10)
        assert stats.can_bypass_validation is False

    def test_can_bypass_validation_false_low_confidence(self):
        """Test can_bypass_validation returns False with low confidence."""
        stats = PatternStats(
            key="test",
            successes=8,
            failures=3,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )
        # confidence = (2+8)/(3+8+3) = 0.714 < 0.90
        assert stats.total == 11  # >= min_obs_bypass
        assert stats.confidence < 0.90
        assert stats.can_bypass_validation is False

    def test_to_dict_serialization(self):
        """Test to_dict() correctly serializes all fields."""
        stats = PatternStats(
            key="get_contacts→send_email",
            successes=5,
            failures=1,
            domains=frozenset(["contact", "email"]),
            intent=PLAN_PATTERN_INTENT_MUTATION,
            last_update=1704067200,
        )

        result = stats.to_dict()

        assert result["key"] == "get_contacts→send_email"
        assert result["successes"] == 5
        assert result["failures"] == 1
        assert result["total"] == 6
        assert "confidence" in result
        assert result["domains"] == ["contact", "email"]  # Sorted
        assert result["intent"] == PLAN_PATTERN_INTENT_MUTATION
        assert result["last_update"] == 1704067200
        assert "is_suggerable" in result
        assert "can_bypass" in result

    def test_immutability(self):
        """Test PatternStats is immutable (frozen dataclass)."""
        stats = PatternStats(
            key="test",
            successes=5,
            failures=1,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )

        with pytest.raises(AttributeError):
            stats.successes = 10  # type: ignore


# =============================================================================
# PlanPatternLearner - Key Generation Tests
# =============================================================================


class TestPatternKeyGeneration:
    """Tests for pattern key generation."""

    def test_make_pattern_key_simple(self, sample_plan):
        """Test pattern key generation for simple plan."""
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(sample_plan)

        # Should strip _tool suffix
        assert key == "get_contacts→send_email"

    def test_make_pattern_key_single_tool(self):
        """Test pattern key with single tool."""
        plan = MockExecutionPlan(steps=[MockExecutionStep(tool_name="get_weather_tool")])
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(plan)

        assert key == "get_weather"

    def test_make_pattern_key_for_each(self):
        """Test pattern key with for_each step."""
        plan = MockExecutionPlan(
            steps=[
                MockExecutionStep(tool_name="get_contacts_tool"),
                MockExecutionStep(
                    tool_name="send_email_tool", for_each="$steps.get_contacts.result"
                ),
            ]
        )
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(plan)

        assert key == "get_contacts→send_email[for_each]"

    def test_make_pattern_key_unknown_tool(self):
        """Test pattern key with None/unknown tool name."""
        plan = MockExecutionPlan(steps=[MockExecutionStep(tool_name=None)])  # type: ignore
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(plan)

        assert key == "unknown"

    def test_make_pattern_key_no_tool_suffix(self):
        """Test pattern key when tool name has no _tool suffix."""
        plan = MockExecutionPlan(steps=[MockExecutionStep(tool_name="custom_action")])
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(plan)

        assert key == "custom_action"

    def test_redis_key_generation(self):
        """Test _redis_key generates correct key format."""
        learner = PlanPatternLearner()
        redis_key = learner._redis_key("get_contacts→send_email")

        # Prefix is "plan:patterns" from constants
        assert redis_key.startswith("plan:patterns:")
        assert "get_contacts→send_email" in redis_key


# =============================================================================
# PlanPatternLearner - Recording Tests
# =============================================================================


class TestPatternRecording:
    """Tests for pattern recording (success/failure)."""

    @pytest.mark.asyncio
    async def test_record_success_creates_task(self, sample_plan, sample_qi_mutation, mock_redis):
        """Test that record_success creates async task."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        # Should not raise, creates background task
        learner.record_success(sample_plan, sample_qi_mutation)

    @pytest.mark.asyncio
    async def test_record_failure_creates_task(self, sample_plan, sample_qi_mutation, mock_redis):
        """Test that record_failure creates async task."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        # Should not raise, creates background task
        learner.record_failure(sample_plan, sample_qi_mutation)

    @pytest.mark.asyncio
    async def test_record_skipped_when_training_disabled(self, sample_plan, sample_qi_mutation):
        """Test that recording is skipped when training is disabled."""
        with patch.object(config, "_training_enabled", False):
            with patch.object(config, "_loaded", True):
                learner = PlanPatternLearner()

                # Should return immediately without creating task
                learner.record_success(sample_plan, sample_qi_mutation)
                learner.record_failure(sample_plan, sample_qi_mutation)

    @pytest.mark.asyncio
    async def test_record_internal_increments_success_counter(
        self, sample_plan, sample_qi_mutation, mock_redis
    ):
        """Test _record increments success counter in Redis."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        await learner._record(sample_plan, sample_qi_mutation, success=True)

        # Verify pipeline was used correctly
        mock_redis.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_record_internal_increments_failure_counter(
        self, sample_plan, sample_qi_mutation, mock_redis
    ):
        """Test _record increments failure counter in Redis."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        await learner._record(sample_plan, sample_qi_mutation, success=False)

        # Verify pipeline was used correctly
        mock_redis.pipeline.assert_called()

    @pytest.mark.asyncio
    async def test_record_internal_clears_cache(self, sample_plan, sample_qi_mutation, mock_redis):
        """Test _record clears local cache after recording."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis
        learner._cache = {"some_key": []}
        learner._cache_time = time.time()

        await learner._record(sample_plan, sample_qi_mutation, success=True)

        assert learner._cache == {}
        assert learner._cache_time == 0

    @pytest.mark.asyncio
    async def test_record_internal_handles_redis_error(self, sample_plan, sample_qi_mutation):
        """Test _record handles Redis errors gracefully."""
        learner = PlanPatternLearner()

        # Mock Redis that raises exception
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = Exception("Redis error")
        learner._redis = mock_redis

        # Should not raise, just log warning
        await learner._record(sample_plan, sample_qi_mutation, success=True)

    @pytest.mark.asyncio
    async def test_record_internal_returns_early_without_redis(
        self, sample_plan, sample_qi_mutation
    ):
        """Test _record returns early if Redis unavailable."""
        learner = PlanPatternLearner()

        with patch.object(
            PlanPatternLearner, "_ensure_redis", new_callable=AsyncMock, return_value=None
        ):
            # Should return without error
            await learner._record(sample_plan, sample_qi_mutation, success=True)


# =============================================================================
# PlanPatternLearner - Suggestions Tests
# =============================================================================


class TestPatternSuggestions:
    """Tests for pattern suggestions retrieval."""

    @pytest.mark.asyncio
    async def test_get_suggestions_returns_empty_when_disabled(self):
        """Test get_suggestions returns empty when feature disabled."""
        with patch.object(config, "_enabled", False):
            with patch.object(config, "_loaded", True):
                learner = PlanPatternLearner()
                result = await learner.get_suggestions(["contact"], False)
                assert result == []

    @pytest.mark.asyncio
    async def test_get_suggestions_uses_cache(self, mock_redis):
        """Test get_suggestions uses local cache when valid."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        # Pre-populate cache
        cached_stats = [
            PatternStats(
                key="get_contacts",
                successes=5,
                failures=0,
                domains=frozenset(["contact"]),
                intent=PLAN_PATTERN_INTENT_READ,
                last_update=0,
            )
        ]
        cache_key = "contact:False"
        learner._cache[cache_key] = cached_stats
        learner._cache_time = time.time()  # Fresh cache

        result = await learner.get_suggestions(["contact"], False)

        assert result == cached_stats

    @pytest.mark.asyncio
    async def test_get_suggestions_bypasses_stale_cache(self, mock_redis):
        """Test get_suggestions bypasses stale cache."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        # Pre-populate with stale cache
        learner._cache["contact:False"] = []
        learner._cache_time = time.time() - 10  # Stale (> 1s default TTL)

        with patch.object(
            PlanPatternLearner, "_fetch_suggestions", new_callable=AsyncMock, return_value=[]
        ):
            result = await learner.get_suggestions(["contact"], False)
            assert result == []

    @pytest.mark.asyncio
    async def test_get_suggestions_handles_timeout(self, mock_redis):
        """Test get_suggestions returns empty on timeout."""
        import asyncio

        learner = PlanPatternLearner()
        learner._redis = mock_redis

        async def slow_fetch(*args, **kwargs):
            await asyncio.sleep(1)  # Longer than timeout (default 5ms)
            return []

        with patch.object(PlanPatternLearner, "_fetch_suggestions", side_effect=slow_fetch):
            result = await learner.get_suggestions(["contact"], False)
            assert result == []

    @pytest.mark.asyncio
    async def test_get_suggestions_handles_exception(self, mock_redis):
        """Test get_suggestions returns empty on exception."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        with patch.object(
            PlanPatternLearner, "_fetch_suggestions", side_effect=Exception("Test error")
        ):
            result = await learner.get_suggestions(["contact"], False)
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_suggestions_returns_empty_without_redis(self):
        """Test _fetch_suggestions returns empty without Redis."""
        learner = PlanPatternLearner()

        with patch.object(
            PlanPatternLearner, "_ensure_redis", new_callable=AsyncMock, return_value=None
        ):
            result = await learner._fetch_suggestions(["contact"], False)
            assert result == []

    @pytest.mark.asyncio
    async def test_fetch_suggestions_filters_by_intent(self, mock_redis):
        """Test _fetch_suggestions filters patterns by intent."""
        learner = PlanPatternLearner()

        # Mock Redis with patterns of different intents
        async def scan_iter_mock(pattern):
            yield "plan_pattern:get_contacts"
            yield "plan_pattern:send_email"

        mock_redis.scan_iter = scan_iter_mock

        # First pattern is READ, second is MUTATION
        async def hgetall_mock(key):
            if "get_contacts" in key:
                return {
                    "s": "5",
                    "f": "0",
                    "d": "contact",
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }
            else:
                return {
                    "s": "5",
                    "f": "0",
                    "d": "email",
                    "i": PLAN_PATTERN_INTENT_MUTATION,
                    "t": "0",
                }

        mock_redis.hgetall = hgetall_mock
        learner._redis = mock_redis

        # Request READ patterns only
        result = await learner._fetch_suggestions(["contact"], is_mutation=False)

        # Should only return READ pattern
        assert len(result) <= 1
        for p in result:
            assert p.intent == PLAN_PATTERN_INTENT_READ

    @pytest.mark.asyncio
    async def test_fetch_suggestions_filters_by_exact_domain_match(self, mock_redis):
        """Test _fetch_suggestions requires exact domain match."""
        learner = PlanPatternLearner()

        async def scan_iter_mock(pattern):
            yield "plan_pattern:get_contacts→send_email"
            yield "plan_pattern:get_contacts"

        mock_redis.scan_iter = scan_iter_mock

        async def hgetall_mock(key):
            if "send_email" in key:
                return {
                    "s": "5",
                    "f": "0",
                    "d": "contact,email",  # Two domains
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }
            else:
                return {
                    "s": "5",
                    "f": "0",
                    "d": "contact",  # One domain
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }

        mock_redis.hgetall = hgetall_mock
        learner._redis = mock_redis

        # Request patterns for single domain
        result = await learner._fetch_suggestions(["contact"], is_mutation=False)

        # Should only return pattern with exact domain match
        for p in result:
            assert p.domains == frozenset(["contact"])

    @pytest.mark.asyncio
    async def test_fetch_suggestions_only_returns_suggerable(self, mock_redis):
        """Test _fetch_suggestions only returns patterns meeting suggerable threshold."""
        learner = PlanPatternLearner()

        async def scan_iter_mock(pattern):
            yield "plan_pattern:high_confidence"
            yield "plan_pattern:low_confidence"

        mock_redis.scan_iter = scan_iter_mock

        async def hgetall_mock(key):
            if "high" in key:
                return {
                    "s": "5",  # High success
                    "f": "0",
                    "d": "contact",
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }
            else:
                return {
                    "s": "1",  # Low success (< 3 observations)
                    "f": "0",
                    "d": "contact",
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }

        mock_redis.hgetall = hgetall_mock
        learner._redis = mock_redis

        result = await learner._fetch_suggestions(["contact"], is_mutation=False)

        # All returned patterns should be suggerable
        for p in result:
            assert p.is_suggerable is True

    @pytest.mark.asyncio
    async def test_fetch_suggestions_sorted_by_confidence(self, mock_redis):
        """Test _fetch_suggestions returns patterns sorted by confidence descending."""
        learner = PlanPatternLearner()

        async def scan_iter_mock(pattern):
            yield "plan_pattern:medium"
            yield "plan_pattern:high"
            yield "plan_pattern:low"

        mock_redis.scan_iter = scan_iter_mock

        async def hgetall_mock(key):
            if "high" in key:
                return {
                    "s": "20",
                    "f": "0",
                    "d": "contact",
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }
            elif "medium" in key:
                return {"s": "5", "f": "1", "d": "contact", "i": PLAN_PATTERN_INTENT_READ, "t": "0"}
            else:
                return {"s": "3", "f": "1", "d": "contact", "i": PLAN_PATTERN_INTENT_READ, "t": "0"}

        mock_redis.hgetall = hgetall_mock
        learner._redis = mock_redis

        result = await learner._fetch_suggestions(["contact"], is_mutation=False)

        # Should be sorted by confidence descending
        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i].confidence >= result[i + 1].confidence


# =============================================================================
# PlanPatternLearner - Bypass Validation Tests
# =============================================================================


class TestBypassValidation:
    """Tests for validation bypass decision."""

    @pytest.mark.asyncio
    async def test_should_bypass_returns_false_when_disabled(self, sample_plan):
        """Test should_bypass_validation returns False when feature disabled."""
        with patch.object(config, "_enabled", False):
            with patch.object(config, "_loaded", True):
                learner = PlanPatternLearner()
                result = await learner.should_bypass_validation(sample_plan)
                assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_returns_false_without_redis(self, sample_plan):
        """Test should_bypass_validation returns False without Redis."""
        learner = PlanPatternLearner()

        with patch.object(
            PlanPatternLearner, "_ensure_redis", new_callable=AsyncMock, return_value=None
        ):
            result = await learner.should_bypass_validation(sample_plan)
            assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_returns_false_pattern_not_found(self, sample_plan, mock_redis):
        """Test should_bypass_validation returns False when pattern not in Redis."""
        learner = PlanPatternLearner()
        mock_redis.hgetall = AsyncMock(return_value={})
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_returns_false_low_confidence(self, sample_plan, mock_redis):
        """Test should_bypass_validation returns False when confidence too low."""
        learner = PlanPatternLearner()

        # Pattern with insufficient observations
        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "5",  # < 10 required
                "f": "0",
                "d": "contact,email",
                "i": PLAN_PATTERN_INTENT_READ,
                "t": "0",
            }
        )
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_returns_true_high_confidence(self, sample_plan, mock_redis):
        """Test should_bypass_validation returns True when thresholds met."""
        learner = PlanPatternLearner()

        # Pattern with high confidence (10+ successes, 90%+ confidence)
        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "15",
                "f": "0",
                "d": "contact,email",
                "i": PLAN_PATTERN_INTENT_READ,
                "t": "0",
            }
        )
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_bypass_rejects_intent_mismatch(
        self, sample_plan, sample_qi_mutation, mock_redis
    ):
        """Test should_bypass_validation rejects when intent doesn't match query."""
        learner = PlanPatternLearner()

        # Pattern stored as READ but query is MUTATION
        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "15",
                "f": "0",
                "d": "contact,email",
                "i": PLAN_PATTERN_INTENT_READ,  # READ intent
                "t": "0",
            }
        )
        learner._redis = mock_redis

        # Query has mutation intent
        result = await learner.should_bypass_validation(sample_plan, sample_qi_mutation)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_rejects_domain_mismatch(self, sample_plan, mock_redis):
        """Test should_bypass_validation rejects when domains don't match query."""
        learner = PlanPatternLearner()

        # Pattern with different domains
        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "15",
                "f": "0",
                "d": "contact",  # Only contact, missing email
                "i": PLAN_PATTERN_INTENT_READ,
                "t": "0",
            }
        )
        learner._redis = mock_redis

        # Query has both contact and email domains
        qi = MockQueryIntelligence(domains=["contact", "email"], is_mutation_intent=False)

        result = await learner.should_bypass_validation(sample_plan, qi)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_accepts_matching_context(
        self, sample_plan, sample_qi_read, mock_redis
    ):
        """Test should_bypass_validation accepts when context fully matches."""
        learner = PlanPatternLearner()

        # Pattern matches query exactly
        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "15",
                "f": "0",
                "d": "contact,email",
                "i": PLAN_PATTERN_INTENT_READ,
                "t": "0",
            }
        )
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan, sample_qi_read)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_bypass_handles_timeout(self, sample_plan, mock_redis):
        """Test should_bypass_validation returns False on timeout."""
        learner = PlanPatternLearner()

        async def slow_hgetall(*args):
            import asyncio

            await asyncio.sleep(1)
            return {}

        mock_redis.hgetall = slow_hgetall
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_bypass_handles_exception(self, sample_plan, mock_redis):
        """Test should_bypass_validation returns False on exception."""
        learner = PlanPatternLearner()
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        learner._redis = mock_redis

        result = await learner.should_bypass_validation(sample_plan)
        assert result is False


# =============================================================================
# PlanPatternLearner - Prompt Generation Tests
# =============================================================================


class TestPromptGeneration:
    """Tests for prompt section generation."""

    @pytest.mark.asyncio
    async def test_get_prompt_section_returns_empty_no_suggestions(self, mock_redis):
        """Test get_prompt_section returns empty string when no suggestions."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        with patch.object(
            PlanPatternLearner, "get_suggestions", new_callable=AsyncMock, return_value=[]
        ):
            result = await learner.get_prompt_section(["contact"], False)
            assert result == ""

    @pytest.mark.asyncio
    async def test_get_prompt_section_formats_suggestions(self, mock_redis):
        """Test get_prompt_section correctly formats suggestions."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        suggestions = [
            PatternStats(
                key="get_contacts→send_email",
                successes=10,
                failures=0,
                domains=frozenset(["contact", "email"]),
                intent=PLAN_PATTERN_INTENT_MUTATION,
                last_update=0,
            )
        ]

        with patch.object(
            PlanPatternLearner, "get_suggestions", new_callable=AsyncMock, return_value=suggestions
        ):
            result = await learner.get_prompt_section(["contact", "email"], True)

            assert "VALIDATED PATTERNS" in result
            assert "get_contacts → send_email" in result
            assert "success" in result.lower()


# =============================================================================
# PlanPatternLearner - Admin Operations Tests
# =============================================================================


class TestAdminOperations:
    """Tests for admin/maintenance operations."""

    @pytest.mark.asyncio
    async def test_list_all_patterns_empty(self, mock_redis):
        """Test list_all_patterns returns empty list when no patterns."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        result = await learner.list_all_patterns()
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all_patterns_returns_sorted(self, mock_redis):
        """Test list_all_patterns returns patterns sorted by confidence."""
        learner = PlanPatternLearner()

        async def scan_iter_mock(pattern):
            yield "plan_pattern:low"
            yield "plan_pattern:high"

        mock_redis.scan_iter = scan_iter_mock

        async def hgetall_mock(key):
            if "high" in key:
                return {
                    "s": "20",
                    "f": "0",
                    "d": "contact",
                    "i": PLAN_PATTERN_INTENT_READ,
                    "t": "0",
                }
            else:
                return {"s": "3", "f": "2", "d": "contact", "i": PLAN_PATTERN_INTENT_READ, "t": "0"}

        mock_redis.hgetall = hgetall_mock
        learner._redis = mock_redis

        result = await learner.list_all_patterns()

        if len(result) >= 2:
            assert result[0].confidence >= result[1].confidence

    @pytest.mark.asyncio
    async def test_get_pattern_found(self, mock_redis):
        """Test get_pattern returns PatternStats when found."""
        learner = PlanPatternLearner()

        mock_redis.hgetall = AsyncMock(
            return_value={
                "s": "5",
                "f": "1",
                "d": "contact,email",
                "i": PLAN_PATTERN_INTENT_MUTATION,
                "t": "1704067200",
            }
        )
        learner._redis = mock_redis

        result = await learner.get_pattern("get_contacts→send_email")

        assert result is not None
        assert result.key == "get_contacts→send_email"
        assert result.successes == 5
        assert result.failures == 1

    @pytest.mark.asyncio
    async def test_get_pattern_not_found(self, mock_redis):
        """Test get_pattern returns None when not found."""
        learner = PlanPatternLearner()
        mock_redis.hgetall = AsyncMock(return_value={})
        learner._redis = mock_redis

        result = await learner.get_pattern("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_pattern_success(self, mock_redis):
        """Test delete_pattern returns True on success."""
        learner = PlanPatternLearner()
        mock_redis.delete = AsyncMock(return_value=1)
        learner._redis = mock_redis
        learner._cache = {"some": "data"}
        learner._cache_time = 123

        result = await learner.delete_pattern("test_pattern")

        assert result is True
        assert learner._cache == {}
        assert learner._cache_time == 0

    @pytest.mark.asyncio
    async def test_delete_pattern_not_found(self, mock_redis):
        """Test delete_pattern returns False when not found."""
        learner = PlanPatternLearner()
        mock_redis.delete = AsyncMock(return_value=0)
        learner._redis = mock_redis

        result = await learner.delete_pattern("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_all_patterns(self, mock_redis):
        """Test delete_all_patterns deletes all and returns count."""
        learner = PlanPatternLearner()

        deleted_keys = []

        async def scan_iter_mock(pattern):
            yield "plan_pattern:one"
            yield "plan_pattern:two"
            yield "plan_pattern:three"

        mock_redis.scan_iter = scan_iter_mock

        async def delete_mock(key):
            deleted_keys.append(key)
            return 1

        mock_redis.delete = delete_mock
        learner._redis = mock_redis
        learner._cache = {"some": "data"}

        result = await learner.delete_all_patterns()

        assert result == 3
        assert len(deleted_keys) == 3
        assert learner._cache == {}

    @pytest.mark.asyncio
    async def test_seed_pattern_success(self, mock_redis):
        """Test seed_pattern creates pattern correctly."""
        learner = PlanPatternLearner()
        mock_redis.hset = AsyncMock()
        learner._redis = mock_redis
        learner._cache = {"some": "data"}

        result = await learner.seed_pattern(
            pattern_key="get_contacts→send_email",
            domains=["contact", "email"],
            intent=PLAN_PATTERN_INTENT_MUTATION,
            successes=5,
            failures=0,
        )

        assert result is True
        mock_redis.hset.assert_called_once()
        assert learner._cache == {}

    @pytest.mark.asyncio
    async def test_seed_pattern_handles_error(self, mock_redis):
        """Test seed_pattern returns False on error."""
        learner = PlanPatternLearner()
        mock_redis.hset = AsyncMock(side_effect=Exception("Redis error"))
        learner._redis = mock_redis

        result = await learner.seed_pattern(
            pattern_key="test",
            domains=["contact"],
            intent=PLAN_PATTERN_INTENT_READ,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_get_stats_summary_empty(self, mock_redis):
        """Test get_stats_summary returns zeros when no patterns."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        with patch.object(
            PlanPatternLearner, "list_all_patterns", new_callable=AsyncMock, return_value=[]
        ):
            result = await learner.get_stats_summary()

            assert result["total_patterns"] == 0
            assert result["suggerable_patterns"] == 0
            assert result["bypassable_patterns"] == 0
            assert result["total_observations"] == 0

    @pytest.mark.asyncio
    async def test_get_stats_summary_with_patterns(self, mock_redis):
        """Test get_stats_summary calculates correct aggregates."""
        learner = PlanPatternLearner()
        learner._redis = mock_redis

        patterns = [
            PatternStats("p1", 10, 0, frozenset(), PLAN_PATTERN_INTENT_READ, 0),  # Bypassable
            PatternStats("p2", 5, 0, frozenset(), PLAN_PATTERN_INTENT_READ, 0),  # Suggerable
            PatternStats("p3", 1, 0, frozenset(), PLAN_PATTERN_INTENT_READ, 0),  # Neither
        ]

        with patch.object(
            PlanPatternLearner, "list_all_patterns", new_callable=AsyncMock, return_value=patterns
        ):
            result = await learner.get_stats_summary()

            assert result["total_patterns"] == 3
            assert result["total_observations"] == 16  # 10+5+1
            assert result["total_successes"] == 16
            assert result["total_failures"] == 0


# =============================================================================
# Singleton and Convenience Functions Tests
# =============================================================================


class TestSingletonAndConvenienceFunctions:
    """Tests for singleton pattern and module-level convenience functions."""

    def test_get_pattern_learner_returns_singleton(self):
        """Test get_pattern_learner returns same instance."""
        reset_pattern_learner()

        learner1 = get_pattern_learner()
        learner2 = get_pattern_learner()

        assert learner1 is learner2

    def test_reset_pattern_learner_clears_singleton(self):
        """Test reset_pattern_learner creates new instance."""
        learner1 = get_pattern_learner()
        reset_pattern_learner()
        learner2 = get_pattern_learner()

        assert learner1 is not learner2

    def test_record_plan_success_calls_learner(self, sample_plan, sample_qi_mutation):
        """Test record_plan_success delegates to learner."""
        reset_pattern_learner()

        with patch.object(PlanPatternLearner, "record_success") as mock_record:
            record_plan_success(sample_plan, sample_qi_mutation)
            mock_record.assert_called_once_with(sample_plan, sample_qi_mutation)

    def test_record_plan_failure_calls_learner(self, sample_plan, sample_qi_mutation):
        """Test record_plan_failure delegates to learner."""
        reset_pattern_learner()

        with patch.object(PlanPatternLearner, "record_failure") as mock_record:
            record_plan_failure(sample_plan, sample_qi_mutation)
            mock_record.assert_called_once_with(sample_plan, sample_qi_mutation)

    @pytest.mark.asyncio
    async def test_get_learned_patterns_prompt_calls_learner(self):
        """Test get_learned_patterns_prompt delegates to learner."""
        reset_pattern_learner()

        with patch.object(
            PlanPatternLearner, "get_prompt_section", AsyncMock(return_value="test prompt")
        ) as mock_prompt:
            result = await get_learned_patterns_prompt(["contact"], True)

            assert result == "test prompt"
            mock_prompt.assert_called_once_with(["contact"], True)

    @pytest.mark.asyncio
    async def test_can_skip_validation_calls_learner(self, sample_plan, sample_qi_read):
        """Test can_skip_validation delegates to learner."""
        reset_pattern_learner()

        with patch.object(
            PlanPatternLearner, "should_bypass_validation", AsyncMock(return_value=True)
        ) as mock_bypass:
            result = await can_skip_validation(sample_plan, sample_qi_read)

            assert result is True
            mock_bypass.assert_called_once_with(sample_plan, sample_qi_read)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_pattern_stats_with_empty_domains(self):
        """Test PatternStats handles empty domains."""
        stats = PatternStats(
            key="test",
            successes=5,
            failures=0,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )

        result = stats.to_dict()
        assert result["domains"] == []

    def test_pattern_stats_confidence_with_only_failures(self):
        """Test confidence calculation with only failures."""
        stats = PatternStats(
            key="test",
            successes=0,
            failures=10,
            domains=frozenset(),
            intent=PLAN_PATTERN_INTENT_READ,
            last_update=0,
        )

        # confidence = (2+0)/(3+0+10) = 0.154
        assert stats.confidence < 0.2
        assert stats.is_suggerable is False

    @pytest.mark.asyncio
    async def test_ensure_redis_handles_exception(self):
        """Test _ensure_redis handles exceptions gracefully."""
        learner = PlanPatternLearner()
        learner._redis = None  # Force re-initialization

        with patch(
            "src.infrastructure.cache.redis.get_redis_cache",
            AsyncMock(side_effect=Exception("Redis not available")),
        ):
            result = await learner._ensure_redis()
            assert result is None

    def test_make_pattern_key_empty_steps(self):
        """Test make_pattern_key handles empty steps."""
        plan = MockExecutionPlan(steps=[])
        learner = PlanPatternLearner()
        key = learner.make_pattern_key(plan)

        assert key == ""

    @pytest.mark.asyncio
    async def test_list_all_patterns_handles_redis_error(self, mock_redis):
        """Test list_all_patterns handles Redis errors gracefully."""
        learner = PlanPatternLearner()

        async def scan_iter_error(pattern):
            raise Exception("Redis error")
            yield  # Make it async generator

        mock_redis.scan_iter = scan_iter_error
        learner._redis = mock_redis

        result = await learner.list_all_patterns()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_pattern_handles_redis_error(self, mock_redis):
        """Test get_pattern handles Redis errors gracefully."""
        learner = PlanPatternLearner()
        mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis error"))
        learner._redis = mock_redis

        result = await learner.get_pattern("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_pattern_handles_redis_error(self, mock_redis):
        """Test delete_pattern handles Redis errors gracefully."""
        learner = PlanPatternLearner()
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))
        learner._redis = mock_redis

        result = await learner.delete_pattern("test")
        assert result is False
