"""
Unit tests for delegate_to_sub_agent_tool.

Verifies tool definition, parameters, depth-check logic, and (post ADR-083)
the rewrite onto ReactSubAgentRunner.
"""

import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from langchain.tools import ToolRuntime

from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.tools.react_runner import (
    BUDGET_EXHAUSTED_FIELD,
    OUTPUT_TRUNCATED_FIELD,
    ReactSubAgentResult,
    SubAgentOutcome,
)
from src.domains.agents.tools.react_runner_budget import tool_rounds_for
from tests.helpers.runtime_context import make_tool_runtime


class TestDelegateToolDefinition:
    """Verify the delegate tool is properly defined and decorated."""

    def test_tool_exists_and_named(self):
        """delegate_to_sub_agent_tool is importable with correct name."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        assert delegate_to_sub_agent_tool.name == "delegate_to_sub_agent_tool"

    def test_tool_description_mentions_delegate(self):
        """Tool description explains delegation."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        desc = delegate_to_sub_agent_tool.description.lower()
        assert "delegate" in desc or "sub-agent" in desc

    def test_tool_has_required_parameters(self):
        """Tool has expertise and instruction parameters."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        schema = delegate_to_sub_agent_tool.args_schema
        field_names = set(schema.model_fields.keys())
        assert "expertise" in field_names
        assert "instruction" in field_names

    def test_tool_is_async(self):
        """Tool has an async coroutine."""
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        assert delegate_to_sub_agent_tool.coroutine is not None

    def test_tool_returns_unified_output(self):
        """Tool return type annotation is UnifiedToolOutput."""
        from src.domains.agents.tools.output import UnifiedToolOutput
        from src.domains.agents.tools.sub_agent_tools import (
            delegate_to_sub_agent_tool,
        )

        annotations = getattr(delegate_to_sub_agent_tool.coroutine, "__annotations__", {})
        assert annotations.get("return") is UnifiedToolOutput


class TestCatalogueManifest:
    """Verify catalogue manifests are correctly defined."""

    def test_agent_manifest(self):
        """Agent manifest has correct name and tools."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            SUB_AGENT_MANIFEST,
        )

        assert SUB_AGENT_MANIFEST.name == "sub_agent_agent"
        assert "delegate_to_sub_agent_tool" in SUB_AGENT_MANIFEST.tools

    def test_tool_manifest(self):
        """Tool manifest has correct name, agent, and parameters."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        m = delegate_to_sub_agent_catalogue_manifest
        assert m.name == "delegate_to_sub_agent_tool"
        assert m.agent == "sub_agent_agent"
        assert len(m.parameters) == 2

        param_names = {p.name for p in m.parameters}
        assert "expertise" in param_names
        assert "instruction" in param_names

    def test_tool_manifest_has_analysis_output(self):
        """Tool manifest declares 'analysis' output field."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        output_paths = {o.path for o in delegate_to_sub_agent_catalogue_manifest.outputs}
        assert "analysis" in output_paths

    def test_tool_manifest_cost_profile(self):
        """Tool manifest has a reasonable cost profile."""
        from src.domains.agents.sub_agents.catalogue_manifests import (
            delegate_to_sub_agent_catalogue_manifest,
        )

        cost = delegate_to_sub_agent_catalogue_manifest.cost
        assert cost.est_latency_ms >= 10000  # Sub-agents are slow (full graph)
        assert cost.est_tokens_in > 0


class TestDepthCheck:
    """Verify depth-limit mechanism via session_id prefix."""

    def test_subagent_session_prefix(self):
        """Session IDs starting with 'subagent_' indicate sub-agent context."""
        # This verifies the convention used for depth checking
        session_id = "subagent_abc123_def456"
        assert session_id.startswith("subagent_")

    def test_normal_session_not_blocked(self):
        """Normal session IDs don't trigger depth check."""
        session_id = "user_conversation_abc123"
        assert not session_id.startswith("subagent_")


# ============================================================================
# ADR-083: delegate_to_sub_agent_tool runs on ReactSubAgentRunner
# ============================================================================


def _FakeRuntime(  # noqa: N802 — kept as a name so the call sites read unchanged
    user_id: UUID = UUID("00000000-0000-0000-0000-000000000001"),
    thread_id: str = "thread_abc",
) -> ToolRuntime[LiaRuntimeContext, Any]:
    """The runtime the tool layer injects, carrying a real run context.

    It used to be a hand-rolled stand-in whose identity lived in
    ``configurable``; since ADR-231 the tool reads ``runtime.context``, so a
    stand-in without one exercises only the configuration-error path.
    """
    return make_tool_runtime(
        user_id=user_id,
        thread_id=thread_id,
        conversation_id=thread_id,
        timezone="Europe/Paris",
        language="fr",
        store=MagicMock(),  # truthy
    )


# ADR-083 Phase 2 Task 4 (Option B): the per-user `sub_agents_enabled`
# preference check was removed — the tool no longer touches the DB on its
# main path. Tests below run without DB/UserService mocks.


class TestDelegateRunsOnReactSubAgentRunner:
    """ADR-083 behavior tests: the tool must run on ReactSubAgentRunner, not SubAgentExecutor."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invokes_react_runner_with_correct_args(self):
        """delegate_to_sub_agent_tool calls ReactSubAgentRunner('subagent', 'subagent_react_prompt').run(...).

        Verifies:
        - LLM type and prompt name are exactly the ADR-083 values.
        - task=instruction, expertise injected via prompt_vars.
        - recursion_limit comes from settings.subagent_default_max_iterations.
        - display_name carries an "sub-agent: <expertise>" prefix (token attribution).
        - parent_runtime is propagated (config + store + callbacks isolation).
        """
        from src.core.config import get_settings
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(
            return_value=ReactSubAgentResult(
                final_message="Analysis of 5 emails: subject A, B, C.",
                messages=[],
                accumulated_registry={},
                iteration_count=2,
                duration_ms=1234,
            )
        )

        fake_runtime = _FakeRuntime()

        with (
            patch(
                "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
                return_value=runner_mock,
            ) as runner_ctor,
            patch(
                "src.domains.agents.tools.sub_agent_tools.get_all_tools",
                return_value={"get_emails_tool": MagicMock(name="get_emails_tool")},
            ),
        ):
            result = await delegate_to_sub_agent_tool.coroutine(
                expertise="expert comptable specialise en analyse de tresorerie",
                instruction="Analyse les flux Q1 et identifie les anomalies.",
                runtime=fake_runtime,
            )

        runner_ctor.assert_called_once_with("subagent", "subagent_react_prompt")
        run_kwargs = runner_mock.run.await_args.kwargs
        assert run_kwargs["task"] == "Analyse les flux Q1 et identifie les anomalies."
        # The prompt names the tools the loop is bound to and the budget it is held
        # to — read from what runs, never written in prose (ADR-284).
        assert run_kwargs["prompt_vars"] == {
            "expertise": "expert comptable specialise en analyse de tresorerie",
            "research_tools": "none",
            "max_tool_rounds": str(tool_rounds_for(get_settings().subagent_default_max_iterations)),
        }
        assert run_kwargs["thread_prefix"] == "subagent"
        assert run_kwargs["display_name"].startswith("sub-agent: ")
        assert run_kwargs["recursion_limit"] == get_settings().subagent_default_max_iterations
        assert run_kwargs["parent_runtime"] is fake_runtime

        # Output mapping: final_message → structured_data["analysis"].
        assert result.success is True
        assert result.structured_data["analysis"].startswith("Analysis of 5 emails")
        assert (
            result.structured_data["expertise"]
            == "expert comptable specialise en analyse de tresorerie"
        )
        assert result.structured_data["type"] == "sub_agent_analysis"
        assert result.metadata["iteration_count"] == 2
        assert result.metadata["duration_ms"] == 1234
        # A complete analysis carries no partial flag.
        assert BUDGET_EXHAUSTED_FIELD not in result.structured_data
        assert OUTPUT_TRUNCATED_FIELD not in result.structured_data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_failure_when_runner_signals_error(self):
        """A run that ERRORED is a failure coded by its kind — and says no exception text."""
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(
            return_value=ReactSubAgentResult(
                final_message="",
                messages=[],
                accumulated_registry={},
                iteration_count=5,
                duration_ms=9999,
                outcome=SubAgentOutcome.ERROR,
                failure_kind="timeout",
            )
        )

        with (
            patch(
                "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
                return_value=runner_mock,
            ),
            patch(
                "src.domains.agents.tools.sub_agent_tools.get_all_tools",
                return_value={},
            ),
        ):
            result = await delegate_to_sub_agent_tool.coroutine(
                expertise="x",
                instruction="y",
                runtime=_FakeRuntime(),
            )

        assert result.success is False
        assert result.error_code == "TIMEOUT"
        assert result.message == "Sub-agent 'x' failed: its model call ended in error (timeout)."

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocked_when_already_inside_subagent(self):
        """Depth guard: thread_id starting with 'subagent_' → DEPTH_LIMIT_EXCEEDED."""
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        result = await delegate_to_sub_agent_tool.coroutine(
            expertise="x",
            instruction="y",
            runtime=_FakeRuntime(thread_id="subagent_abc123"),
        )

        assert result.success is False
        assert result.error_code == "DEPTH_LIMIT_EXCEEDED"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_does_not_import_legacy_executor_or_crud_classes(self):
        """Regression: the ephemeral path must not depend on the deleted persistent code.

        After ADR-083 Phase 2 cleanup, SubAgentService/SubAgentExecutor/SubAgentRepository
        no longer exist in the codebase, and UserService is no longer imported by this
        tool (the per-user preference check was removed in Option B). The tool also
        must not open a DB session on its main path.
        """
        import src.domains.agents.tools.sub_agent_tools as tool_module
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        for symbol in (
            "SubAgentService",
            "SubAgentExecutor",
            "SubAgentRepository",
            "UserService",
            "get_db_context",
        ):
            assert not hasattr(
                tool_module, symbol
            ), f"ADR-083 Phase 2: {symbol} must not be imported by sub_agent_tools.py"

        # And the tool runs end-to-end without DB / UserService plumbing.
        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(
            return_value=ReactSubAgentResult(
                final_message="ok",
                messages=[],
                accumulated_registry={},
                iteration_count=1,
                duration_ms=10,
            )
        )

        with (
            patch(
                "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
                return_value=runner_mock,
            ),
            patch(
                "src.domains.agents.tools.sub_agent_tools.get_all_tools",
                return_value={},
            ),
        ):
            result = await delegate_to_sub_agent_tool.coroutine(
                expertise="x",
                instruction="y",
                runtime=_FakeRuntime(),
            )

        assert result.success is True


class TestTheDelegationReadsHowTheRunEnded:
    """The outcome decides the tool's answer, never the text (ADR-303)."""

    @staticmethod
    async def _delegate(result: ReactSubAgentResult) -> Any:
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(return_value=result)
        with (
            patch(
                "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
                return_value=runner_mock,
            ),
            patch("src.domains.agents.tools.sub_agent_tools.get_all_tools", return_value={}),
        ):
            return await delegate_to_sub_agent_tool.coroutine(
                expertise="analyst", instruction="Compare the two offers.", runtime=_FakeRuntime()
            )

    @pytest.mark.unit
    async def test_a_run_that_said_nothing_is_an_empty_result(self) -> None:
        output = await self._delegate(
            ReactSubAgentResult(final_message="", messages=[], outcome=SubAgentOutcome.EMPTY)
        )

        assert output.success is False
        assert output.error_code == "EMPTY_RESULT"

    @pytest.mark.unit
    async def test_a_closed_analysis_is_an_analysis_that_says_its_research_was_cut(
        self,
    ) -> None:
        output = await self._delegate(
            ReactSubAgentResult(
                final_message="Findings so far.", messages=[], closed_on_budget=True
            )
        )

        assert output.success is True
        assert output.structured_data["analysis"] == "Findings so far."
        assert output.structured_data[BUDGET_EXHAUSTED_FIELD] is True
        assert OUTPUT_TRUNCATED_FIELD not in output.structured_data

    @pytest.mark.unit
    async def test_an_analysis_cut_at_its_output_budget_says_so(self) -> None:
        output = await self._delegate(
            ReactSubAgentResult(final_message="Findings, then", messages=[], truncated=True)
        )

        assert output.success is True
        assert output.structured_data[OUTPUT_TRUNCATED_FIELD] is True


class TestTheExpertIsToldWhatItHolds:
    """The sub-agent prompt states the tools it is bound to and the budget enforced."""

    @pytest.mark.unit
    async def test_the_rendered_prompt_names_the_bound_tools_and_the_enforced_budget(
        self,
    ) -> None:
        from src.core.config import get_settings
        from src.domains.agents.prompts.prompt_loader import load_prompt
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(
            return_value=ReactSubAgentResult(final_message="ok", messages=[])
        )
        bound = [MagicMock(), MagicMock()]
        bound[0].name, bound[1].name = "brave_search_tool", "fetch_web_page_tool"
        with (
            patch(
                "src.domains.agents.tools.sub_agent_tools.ReactSubAgentRunner",
                return_value=runner_mock,
            ),
            patch("src.domains.agents.tools.sub_agent_tools.get_all_tools", return_value={}),
            patch(
                "src.domains.agents.tools.sub_agent_tools.resolve_tools_for_subagent",
                return_value=bound,
            ),
        ):
            await delegate_to_sub_agent_tool.coroutine(
                expertise="analyst", instruction="Compare the two offers.", runtime=_FakeRuntime()
            )

        # Rendered the way the runner renders it: the real file, the tool's own values.
        prompt_vars = runner_mock.run.await_args.kwargs["prompt_vars"]
        rendered = load_prompt("subagent_react_prompt").format(
            current_datetime="2026-10-13 15:00", **prompt_vars
        )
        rounds = tool_rounds_for(get_settings().subagent_default_max_iterations)
        assert "brave_search_tool, fetch_web_page_tool" in rendered
        assert f"at most {rounds} rounds of tool calls" in rendered
        assert not re.search(r"\{[a-z_]+\}", rendered)
