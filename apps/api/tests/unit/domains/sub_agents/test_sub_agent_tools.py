"""
Unit tests for delegate_to_sub_agent_tool.

Verifies tool definition, parameters, depth-check logic, and (post ADR-083)
the rewrite onto ReactSubAgentRunner.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


class _FakeRuntime:
    """Minimal ToolRuntime stand-in (dict-shaped config + truthy store)."""

    def __init__(
        self,
        user_id: str = "00000000-0000-0000-0000-000000000001",
        thread_id: str = "thread_abc",
    ) -> None:
        self.config = {
            "configurable": {
                "user_id": user_id,
                "thread_id": thread_id,
                "user_timezone": "Europe/Paris",
                "user_language": "fr",
            },
            "metadata": {},
            "callbacks": [],
        }
        self.store = MagicMock()  # truthy


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
            return_value=SimpleNamespace(
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
        assert run_kwargs["prompt_vars"] == {
            "expertise": "expert comptable specialise en analyse de tresorerie"
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

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_failure_when_runner_signals_error(self):
        """If ReactSubAgentRunner.run returns final_message starting with 'Error:', tool returns failure."""
        from src.domains.agents.tools.sub_agent_tools import delegate_to_sub_agent_tool

        runner_mock = MagicMock()
        runner_mock.run = AsyncMock(
            return_value=SimpleNamespace(
                final_message="Error: GraphRecursionError: limit reached",
                messages=[],
                accumulated_registry={},
                iteration_count=5,
                duration_ms=9999,
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
        assert result.error_code == "EXECUTION_FAILED"
        assert "did not complete" in (result.message or "")

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
            return_value=SimpleNamespace(
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
