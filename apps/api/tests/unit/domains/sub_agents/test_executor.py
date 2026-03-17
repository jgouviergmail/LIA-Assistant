"""
Unit tests for SubAgentExecutor.

Tests pre-execution validation, daily budget, cancel mechanism,
and the simplified direct pipeline helpers (formatting, analysis).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.sub_agents.executor import (
    SubAgentExecutor,
    _cancel_events,
    _format_completed_steps,
)
from src.domains.sub_agents.models import SubAgentStatus


@pytest.fixture
def executor():
    """Fresh executor instance."""
    return SubAgentExecutor()


@pytest.fixture
def mock_subagent():
    """Mock SubAgent in READY state."""
    agent = MagicMock()
    agent.id = uuid4()
    agent.user_id = uuid4()
    agent.name = "Test Agent"
    agent.is_enabled = True
    agent.status = SubAgentStatus.READY.value
    agent.system_prompt = "You are helpful."
    agent.personality_instruction = None
    agent.context_instructions = None
    agent.last_execution_summary = None
    agent.timeout_seconds = 120
    agent.max_iterations = 5
    agent.skill_ids = []
    agent.allowed_tools = []
    agent.blocked_tools = ["send_email_tool"]
    return agent


class TestValidatePreExecution:
    """Tests for _validate_pre_execution()."""

    def test_valid_subagent(self, mock_subagent):
        """No exception for valid sub-agent."""
        SubAgentExecutor._validate_can_execute(mock_subagent)

    def test_disabled_subagent(self, mock_subagent):
        """Raise ValidationError for disabled sub-agent."""
        from src.core.exceptions import ValidationError

        mock_subagent.is_enabled = False
        with pytest.raises(ValidationError, match="disabled"):
            SubAgentExecutor._validate_can_execute(mock_subagent)

    def test_executing_subagent(self, mock_subagent):
        """Raise ResourceConflictError for already-executing sub-agent."""
        from src.core.exceptions import ResourceConflictError

        mock_subagent.status = SubAgentStatus.EXECUTING.value
        with pytest.raises(ResourceConflictError, match="already executing"):
            SubAgentExecutor._validate_can_execute(mock_subagent)


class TestDailyBudget:
    """Tests for daily budget check and increment."""

    @patch("src.infrastructure.cache.redis.get_redis_cache", new_callable=AsyncMock)
    async def test_budget_ok(self, mock_get_redis):
        """Allow execution when under budget."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"10000"
        mock_get_redis.return_value = mock_redis

        # Should not raise
        await SubAgentExecutor._check_daily_budget(uuid4())

    @patch("src.infrastructure.cache.redis.get_redis_cache", new_callable=AsyncMock)
    async def test_budget_exceeded(self, mock_get_redis):
        """Raise ValidationError when budget exceeded."""
        from src.core.exceptions import ValidationError

        mock_redis = AsyncMock()
        mock_redis.get.return_value = b"999999"
        mock_get_redis.return_value = mock_redis

        with pytest.raises(ValidationError, match="budget exceeded"):
            await SubAgentExecutor._check_daily_budget(uuid4())

    @patch("src.infrastructure.cache.redis.get_redis_cache", new_callable=AsyncMock)
    async def test_budget_redis_failure_continues(self, mock_get_redis):
        """Redis failure doesn't block execution."""
        mock_get_redis.side_effect = ConnectionError("Redis down")

        # Should not raise — graceful degradation
        await SubAgentExecutor._check_daily_budget(uuid4())

    @patch("src.infrastructure.cache.redis.get_redis_cache", new_callable=AsyncMock)
    async def test_increment_budget(self, mock_get_redis):
        """Increment daily budget via Redis INCRBY + TTL."""
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipe
        mock_get_redis.return_value = mock_redis

        await SubAgentExecutor._increment_daily_budget(uuid4(), 5000)

        mock_pipe.incrby.assert_called_once()
        mock_pipe.expire.assert_called_once()
        mock_pipe.execute.assert_called_once()

    async def test_increment_zero_tokens_skipped(self):
        """Skip increment when tokens <= 0."""
        # Should not attempt Redis connection
        await SubAgentExecutor._increment_daily_budget(uuid4(), 0)


class TestCancelExecution:
    """Tests for cancel_execution()."""

    def test_cancel_running(self):
        """Cancel a running execution."""
        import asyncio

        subagent_id = uuid4()
        event = asyncio.Event()
        _cancel_events[subagent_id] = event

        result = SubAgentExecutor.cancel_execution(subagent_id)

        assert result is True
        assert event.is_set()

        # Cleanup
        _cancel_events.pop(subagent_id, None)

    def test_cancel_not_running(self):
        """Return False when no running execution."""
        result = SubAgentExecutor.cancel_execution(uuid4())
        assert result is False

    def test_cancel_already_cancelled(self):
        """Return False when already cancelled."""
        import asyncio

        subagent_id = uuid4()
        event = asyncio.Event()
        event.set()  # Already cancelled
        _cancel_events[subagent_id] = event

        result = SubAgentExecutor.cancel_execution(subagent_id)
        assert result is False

        # Cleanup
        _cancel_events.pop(subagent_id, None)


# ============================================================================
# Direct pipeline helpers
# ============================================================================


class TestAnalyzeInstruction:
    """Tests for _analyze_instruction() LLM-based domain detection."""

    @patch(
        "src.domains.agents.services.query_analyzer_service.analyze_query",
        new_callable=AsyncMock,
    )
    async def test_success_returns_qi_with_detected_domains(self, mock_analyze):
        """Successful analysis returns QI with LLM-detected domains."""
        from dataclasses import dataclass, field

        @dataclass
        class MockAnalysis:
            intent: str = "action"
            primary_domain: str = "web_search"
            secondary_domains: list = field(default_factory=lambda: ["route"])
            confidence: float = 0.9
            english_query: str = "compare trains Paris Strasbourg"
            resolved_references: list = field(default_factory=list)
            reasoning: str = "transport comparison"
            for_each_detected: bool = False
            for_each_collection_key: str | None = None
            cardinality_magnitude: int | None = None

            @property
            def domains(self):
                return [self.primary_domain] + self.secondary_domains

        mock_analyze.return_value = MockAnalysis()

        from src.domains.sub_agents.executor import _analyze_instruction

        qi = await _analyze_instruction(
            instruction="Compare trains Paris Strasbourg",
            expertise="transport specialist",
            user_language="fr",
            config={"configurable": {}},
        )
        assert qi.original_query == "Compare trains Paris Strasbourg"
        assert "web_search" in qi.domains
        assert "route" in qi.domains
        assert qi.is_mutation_intent is False
        assert qi.user_language == "fr"

    @patch(
        "src.domains.agents.services.query_analyzer_service.analyze_query",
        side_effect=RuntimeError("LLM unavailable"),
    )
    async def test_fallback_on_failure(self, mock_analyze):
        """Falls back to web_search domain when analysis fails."""
        from src.domains.sub_agents.executor import _analyze_instruction

        qi = await _analyze_instruction(
            instruction="Some instruction",
            expertise="some expertise",
            user_language="en",
            config={"configurable": {}},
        )
        assert qi.domains == ["web_search"]
        assert qi.immediate_intent == "search"


class TestFormatCompletedSteps:
    """Tests for _format_completed_steps().

    Parallel executor stores results as:
    - Error: {"success": False, "error": "..."}
    - Success structured: {"synthesis": "...", ...} (directly)
    - Success empty: {"success": True}
    """

    def test_empty_steps(self):
        """Empty dict returns placeholder."""
        assert _format_completed_steps({}) == "(no results)"

    def test_error_step(self):
        """Error steps are formatted with ERROR prefix."""
        result = _format_completed_steps(
            {
                "step_1": {"success": False, "error": "API timeout"},
            }
        )
        assert "[step_1] ERROR: API timeout" in result

    def test_synthesis_extraction(self):
        """Extract 'synthesis' field from structured data (direct format)."""
        result = _format_completed_steps(
            {
                "step_1": {"synthesis": "Paris-Lyon takes 2h by TGV"},
            }
        )
        assert "Paris-Lyon takes 2h by TGV" in result

    def test_empty_success(self):
        """Handle empty success result."""
        result = _format_completed_steps(
            {
                "step_1": {"success": True},
            }
        )
        assert "(completed, no data)" in result

    def test_json_fallback(self):
        """Fall back to JSON dump for unknown dict structure."""
        result = _format_completed_steps(
            {
                "step_1": {"custom_key": "custom_value", "count": 42},
            }
        )
        assert "custom_key" in result
        assert "custom_value" in result

    def test_multiple_steps(self):
        """Format multiple steps separated by blank lines."""
        result = _format_completed_steps(
            {
                "step_1": {"synthesis": "Result A"},
                "step_2": {"synthesis": "Result B"},
            }
        )
        assert "[step_1]" in result
        assert "[step_2]" in result
        assert "Result A" in result
        assert "Result B" in result
