"""
Unit tests for SubAgentTokenGuard.

Tests token budget monitoring and abort signaling.
"""

from unittest.mock import MagicMock

from src.domains.sub_agents.token_guard import SubAgentTokenGuard


class TestSubAgentTokenGuard:
    """Tests for SubAgentTokenGuard."""

    def _make_tracker(self, cumulative: int) -> MagicMock:
        tracker = MagicMock()
        tracker.get_cumulative_tokens.return_value = cumulative
        return tracker

    def test_under_budget(self):
        """No abort when under budget."""
        tracker = self._make_tracker(1000)
        guard = SubAgentTokenGuard(max_tokens=5000, tracker=tracker)
        guard.check_and_abort_if_exceeded()

        assert not guard.abort_event.is_set()
        assert guard.tokens_consumed == 1000

    def test_over_budget_triggers_abort(self):
        """Abort event is set when over budget."""
        tracker = self._make_tracker(6000)
        guard = SubAgentTokenGuard(max_tokens=5000, tracker=tracker)
        guard.check_and_abort_if_exceeded()

        assert guard.abort_event.is_set()
        assert guard.tokens_consumed == 6000

    def test_exactly_at_budget(self):
        """No abort when exactly at budget."""
        tracker = self._make_tracker(5000)
        guard = SubAgentTokenGuard(max_tokens=5000, tracker=tracker)
        guard.check_and_abort_if_exceeded()

        assert not guard.abort_event.is_set()

    def test_get_callback(self):
        """get_callback() returns a LangChain BaseCallbackHandler."""
        tracker = self._make_tracker(0)
        guard = SubAgentTokenGuard(max_tokens=5000, tracker=tracker)
        callback = guard.get_callback()

        assert hasattr(callback, "on_llm_end")

    def test_callback_triggers_check(self):
        """Callback's on_llm_end triggers check_and_abort_if_exceeded."""
        tracker = self._make_tracker(10000)
        guard = SubAgentTokenGuard(max_tokens=5000, tracker=tracker)
        callback = guard.get_callback()

        # Simulate LLM completion
        mock_response = MagicMock()
        callback.on_llm_end(mock_response)

        assert guard.abort_event.is_set()
        assert guard.tokens_consumed == 10000
