"""
Unit tests for ReactSubAgentRunner.

Tests the generic ReAct sub-agent runner used by browser_task_tool
and mcp_server_task_tool.

Phase: ADR-062 — Agent Initiative Phase + MCP Iterative Support
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.tools.react_runner import (
    ReactSubAgentResult,
    ReactSubAgentRunner,
    _default_registry_collector,
)


@pytest.mark.unit
class TestReactSubAgentResult:
    """Tests for ReactSubAgentResult dataclass."""

    def test_default_values(self) -> None:
        result = ReactSubAgentResult(final_message="test", messages=[])
        assert result.final_message == "test"
        assert result.accumulated_registry == {}
        assert result.iteration_count == 0
        assert result.duration_ms == 0

    def test_frozen(self) -> None:
        result = ReactSubAgentResult(final_message="test", messages=[])
        with pytest.raises(AttributeError):
            result.final_message = "changed"


@pytest.mark.unit
class TestDefaultRegistryCollector:
    """Tests for _default_registry_collector."""

    def test_empty_tools(self) -> None:
        assert _default_registry_collector([]) == {}

    def test_tools_without_registry(self) -> None:
        tool = MagicMock()
        del tool._accumulated_registry
        assert _default_registry_collector([tool]) == {}

    def test_tools_with_registry(self) -> None:
        tool1 = MagicMock()
        tool1._accumulated_registry = {"item1": {"type": "MCP_APP"}}
        tool2 = MagicMock()
        tool2._accumulated_registry = {"item2": {"type": "CONTACT"}}

        result = _default_registry_collector([tool1, tool2])
        assert "item1" in result
        assert "item2" in result

    def test_tools_with_empty_registry(self) -> None:
        tool = MagicMock()
        tool._accumulated_registry = {}
        assert _default_registry_collector([tool]) == {}


@pytest.mark.unit
class TestReactSubAgentRunner:
    """Tests for ReactSubAgentRunner."""

    @pytest.fixture
    def runner(self) -> ReactSubAgentRunner:
        return ReactSubAgentRunner("test_agent", "test_prompt")

    @patch("src.domains.agents.tools.react_runner.create_react_agent")
    @patch("src.domains.agents.tools.react_runner.load_prompt")
    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_run_basic(
        self,
        mock_get_llm: MagicMock,
        mock_load_prompt: MagicMock,
        mock_create_react: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm
        mock_load_prompt.return_value.format.return_value = "formatted prompt"

        mock_ai_msg = MagicMock()
        mock_ai_msg.content = "Final answer"
        mock_ai_msg.tool_calls = []

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [mock_ai_msg]}
        mock_create_react.return_value = mock_agent

        result = await runner.run(
            task="test task",
            tools=[],
            prompt_vars={"server_name": "test"},
        )

        assert result.final_message == "Final answer"
        assert result.iteration_count == 0
        assert result.duration_ms >= 0

    @patch("src.domains.agents.tools.react_runner.create_react_agent")
    @patch("src.domains.agents.tools.react_runner.load_prompt")
    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_run_error_returns_gracefully(
        self,
        mock_get_llm: MagicMock,
        mock_load_prompt: MagicMock,
        mock_create_react: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        mock_get_llm.return_value = MagicMock()
        mock_load_prompt.return_value.format.return_value = "prompt"

        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("Connection failed")
        mock_create_react.return_value = mock_agent

        result = await runner.run(
            task="test task",
            tools=[],
            prompt_vars={},
        )

        assert "Error" in result.final_message
        assert result.messages == []
        assert result.iteration_count == 0

    @patch("src.domains.agents.tools.react_runner.create_react_agent")
    @patch("src.domains.agents.tools.react_runner.load_prompt")
    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_run_counts_iterations(
        self,
        mock_get_llm: MagicMock,
        mock_load_prompt: MagicMock,
        mock_create_react: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        mock_get_llm.return_value = MagicMock()
        mock_load_prompt.return_value.format.return_value = "prompt"

        msg_with_calls = MagicMock()
        msg_with_calls.content = "Calling tool"
        msg_with_calls.tool_calls = [{"name": "read_me"}]

        msg_final = MagicMock()
        msg_final.content = "Done"
        msg_final.tool_calls = []

        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [msg_with_calls, msg_with_calls, msg_final]}
        mock_create_react.return_value = mock_agent

        result = await runner.run(
            task="test",
            tools=[],
            prompt_vars={},
        )

        assert result.iteration_count == 2
        assert result.final_message == "Done"


@pytest.mark.unit
class TestReactSubAgentMetrics:
    """Tests for the Prometheus instrumentation emitted by ReactSubAgentRunner.

    The ``subagent_active_count`` gauge is global and shared across the process,
    so every assertion compares a before/after delta rather than an absolute
    value. The key invariant is that the gauge is always balanced (incremented
    on spawn, decremented in ``finally``) on every exit path.
    """

    @staticmethod
    def _sample(name: str, labels: dict[str, str] | None = None) -> float:
        """Return a Prometheus sample value (0.0 when the series is absent)."""
        return REGISTRY.get_sample_value(name, labels) or 0.0

    @pytest.fixture
    def runner(self) -> ReactSubAgentRunner:
        return ReactSubAgentRunner("test_agent", "test_prompt")

    @patch("src.domains.agents.tools.react_runner.create_react_agent")
    @patch("src.domains.agents.tools.react_runner.load_prompt")
    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_success_emits_spawn_tokens_and_balances_active(
        self,
        mock_get_llm: MagicMock,
        mock_load_prompt: MagicMock,
        mock_create_react: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        mock_get_llm.return_value = MagicMock()
        mock_load_prompt.return_value.format.return_value = "prompt"
        ai_msg = MagicMock()
        ai_msg.content = "ok"
        ai_msg.tool_calls = []
        ai_msg.usage_metadata = {"input_tokens": 12, "output_tokens": 5}
        mock_agent = AsyncMock()
        mock_agent.ainvoke.return_value = {"messages": [ai_msg]}
        mock_create_react.return_value = mock_agent

        active_before = self._sample("subagent_active_count")
        spawned_before = self._sample(
            "subagent_spawned_total", {"agent_name": "test_agent", "mode": "sync"}
        )
        tokens_in_before = self._sample("subagent_tokens_in_total", {"agent_name": "test_agent"})

        await runner.run(task="t", tools=[], prompt_vars={})

        assert self._sample("subagent_active_count") == pytest.approx(active_before)
        assert self._sample(
            "subagent_spawned_total", {"agent_name": "test_agent", "mode": "sync"}
        ) == pytest.approx(spawned_before + 1)
        assert self._sample(
            "subagent_tokens_in_total", {"agent_name": "test_agent"}
        ) == pytest.approx(tokens_in_before + 12)

    @patch("src.domains.agents.tools.react_runner.create_react_agent")
    @patch("src.domains.agents.tools.react_runner.load_prompt")
    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_ainvoke_error_emits_error_and_balances_active(
        self,
        mock_get_llm: MagicMock,
        mock_load_prompt: MagicMock,
        mock_create_react: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        mock_get_llm.return_value = MagicMock()
        mock_load_prompt.return_value.format.return_value = "prompt"
        mock_agent = AsyncMock()
        mock_agent.ainvoke.side_effect = RuntimeError("boom")
        mock_create_react.return_value = mock_agent

        active_before = self._sample("subagent_active_count")
        errors_before = self._sample(
            "subagent_errors_total", {"agent_name": "test_agent", "error_type": "RuntimeError"}
        )

        result = await runner.run(task="t", tools=[], prompt_vars={})

        assert result.final_message.startswith("Error:")
        assert self._sample("subagent_active_count") == pytest.approx(active_before)
        assert self._sample(
            "subagent_errors_total", {"agent_name": "test_agent", "error_type": "RuntimeError"}
        ) == pytest.approx(errors_before + 1)

    @patch("src.domains.agents.tools.react_runner.get_llm")
    async def test_setup_failure_propagates_and_balances_active(
        self,
        mock_get_llm: MagicMock,
        runner: ReactSubAgentRunner,
    ) -> None:
        # A setup failure (get_llm raising) must propagate to the caller AND the
        # active-count gauge must still be decremented by the finally block — the
        # regression guard for the gauge-leak bug.
        mock_get_llm.side_effect = RuntimeError("llm unavailable")

        active_before = self._sample("subagent_active_count")

        with pytest.raises(RuntimeError, match="llm unavailable"):
            await runner.run(task="t", tools=[], prompt_vars={})

        assert self._sample("subagent_active_count") == pytest.approx(active_before)
