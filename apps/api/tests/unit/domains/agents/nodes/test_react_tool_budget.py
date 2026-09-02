"""A budget that counts only the reasoning bounds only half the turn (ADR-256).

Measured before the fix, on the real constants:

- ``react_elapsed_seconds`` was charged by ONE node out of four, and that node
  is the one that only thinks. ``react_execute_tools_node`` charged nothing.
- ``compute_step_timeout`` — the per-family policy — had a single caller,
  ``parallel_executor``. ``react_nodes`` contained no ``asyncio.wait_for`` at
  all, so the SAME tool was bounded at 300 s in pipeline mode and unbounded in
  ReAct.
- A sub-agent, an iterative MCP task and a browser run each open their own LLM
  loop (20, 50 and 50 iterations) behind one ``tool_call``, and none of them
  charged a second to the parent. Upper bound for one turn: ~30 h.

The two counter-hypotheses were tested and refuted: the repetition brake only
catches IDENTICAL calls (two delegations never look alike), and the per-slot LLM
transport timeout still allows 20 x 60 s for a single delegation.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

from src.core.config import settings
from src.domains.agents.nodes import react_nodes
from src.domains.agents.utils.react_budget import (
    TIMEOUT_ATTRIBUTION_MARGIN,
    loop_compute_seconds,
    loop_tool_seconds,
    react_exit_reason,
    tool_timeout_message,
)

pytestmark = [pytest.mark.unit]


def _state(*, iteration: int = 1, compute: float = 0.0, tool: float = 0.0) -> dict[str, Any]:
    return {
        "react_iteration": iteration,
        "react_max_iterations_effective": 90,
        "react_productive_iterations": 0,
        "react_elapsed_seconds": compute,
        "react_tool_seconds": tool,
    }


class TestTheDelegatedHalfIsNowBounded:
    """The defect: three hours of tool work left the predicate silent."""

    def test_long_tool_work_now_ends_the_turn(self) -> None:
        state = _state(compute=10.0, tool=float(settings.react_tool_budget_seconds) + 1.0)

        assert react_exit_reason(state) == "tool_budget"

    def test_it_is_named_apart_from_the_reasoning_budget(self) -> None:
        """Reporting delegated time as ``compute_budget`` would tell the user the
        model thought too long when in fact a sub-agent did — the invented
        diagnosis ADR-182 removed, pointing the other way."""
        reasoning = _state(compute=float(settings.react_agent_timeout_seconds) + 1.0)
        delegated = _state(compute=10.0, tool=float(settings.react_tool_budget_seconds) + 1.0)

        assert react_exit_reason(reasoning) == "compute_budget"
        assert react_exit_reason(delegated) == "tool_budget"

    def test_the_two_budgets_read_two_different_keys(self) -> None:
        assert loop_compute_seconds({"react_elapsed_seconds": 7.0}) == 7.0
        assert loop_tool_seconds({"react_tool_seconds": 11.0}) == 11.0
        assert loop_tool_seconds({}) == 0.0


class TestNoTurnThatCompletesTodayIsCut:
    """The non-regression requirement, stated as tests.

    Summing tool time into ``react_elapsed_seconds`` was measured and rejected:
    ONE delegation at its pipeline bound (300 s) equals 100 % of the reasoning
    budget (300 s), so turns that finish today would start being truncated.
    """

    def test_the_reasoning_threshold_is_untouched(self) -> None:
        just_under = _state(compute=float(settings.react_agent_timeout_seconds))

        assert react_exit_reason(just_under) is None

    def test_a_long_tool_run_does_not_consume_the_reasoning_budget(self) -> None:
        """300 s of delegated work, 5 s of thinking: the turn continues."""
        state = _state(compute=5.0, tool=300.0)

        assert react_exit_reason(state) is None

    def test_an_absent_key_never_ends_a_turn(self) -> None:
        """A checkpoint written before this change carries no tool seconds.

        Additive and fail-open, exactly like ADR-170's own migration: a resumed
        turn is never cut by state it never had.
        """
        legacy = {"react_iteration": 1, "react_max_iterations_effective": 90}

        assert react_exit_reason(legacy) is None

    def test_zero_is_not_an_overrun(self) -> None:
        assert react_exit_reason(_state(tool=0.0)) is None

    def test_iterations_still_win_over_both_time_budgets(self) -> None:
        """Order matters: the iteration ceiling is checked first, so a turn that
        hits both reports the reason ADR-248's directive already explains."""
        state = _state(iteration=90, compute=1e6, tool=1e6)

        assert react_exit_reason(state) == "max_iterations"


class TestParityWithThePipeline:
    """The per-family timeout policy must have TWO callers, not two copies."""

    def test_react_bounds_tool_execution_with_the_shared_policy(self) -> None:
        source = inspect.getsource(react_nodes.react_execute_tools_node)

        assert "compute_step_timeout" in source, (
            "the pipeline bounds every tool family and ReAct bounded none; "
            "a second copy of the policy would drift from the first"
        )
        assert "wait_for" in source, "the computed bound must actually be applied"

    def test_react_charges_the_time_it_spends_in_tools(self) -> None:
        source = inspect.getsource(react_nodes.react_execute_tools_node)

        assert (
            "react_tool_seconds" in source
        ), "the node that spends the most was the one charging nothing"

    def test_a_timeout_is_recoverable_not_fatal(self) -> None:
        """A tool that overruns must hand the model a message it can act on,
        the way the pipeline turns a step timeout into a failed StepResult."""
        source = inspect.getsource(react_nodes.react_execute_tools_node)

        assert "TimeoutError" in source


class TestTheSharedPolicyIsUnchanged:
    """ReAct reads the policy; it must not redefine any of its values."""

    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("delegate_to_sub_agent_tool", "subagent_tool_timeout_seconds"),
            ("browser_task_tool", "browser_tool_timeout_seconds"),
        ],
    )
    def test_the_bound_comes_from_settings(self, tool_name: str, expected: str) -> None:
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout(tool_name, None) > 0
        assert hasattr(settings, expected)

    def test_an_unknown_tool_gets_the_generic_bound(self) -> None:
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout("some_unlisted_tool", None) == pytest.approx(
            float(settings.default_tool_timeout_seconds)
        )


class TestTimeoutSemantics:
    """asyncio.wait_for raises the builtin TimeoutError on 3.11+."""

    async def test_wait_for_raises_timeout_error(self) -> None:
        async def _slow() -> None:
            await asyncio.sleep(10)

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(_slow(), timeout=0.01)


class TestAnMcpCallKeepsItsOwnBound:
    """Our bound must never be STRICTER than the one the layer below applies.

    Every MCP call is already wrapped in an ``asyncio.wait_for`` by the MCP
    layer itself: ``client_manager`` uses ``mcp_tool_timeout_seconds`` for admin
    servers, and a user server carries its own ``timeout_seconds`` (5..120,
    default 120) that the owner sets. Giving those tools the generic 30 s floor
    would override a setting the user chose — a regression, and a second
    authority on a question that already has one.
    """

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp_excalidraw_create_view",
            "mcp_user_770baa3e_get_indicator",
            "mcp_google_flights_search_flights",
        ],
    )
    def test_a_direct_mcp_call_gets_the_mcp_bound(self, tool_name: str) -> None:
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout(tool_name, None) == pytest.approx(
            float(settings.mcp_tool_timeout_seconds)
        )

    def test_the_mcp_bound_is_never_below_what_a_user_may_configure(self) -> None:
        """A user server accepts up to 120 s; our bound must cover that."""
        from src.domains.user_mcp.schemas import UserMCPServerCreate

        field = UserMCPServerCreate.model_fields["timeout_seconds"]
        user_max = next(m.le for m in field.metadata if getattr(m, "le", None) is not None)

        assert float(settings.mcp_tool_timeout_seconds) >= float(user_max)

    def test_the_iterative_task_tool_keeps_its_own_family(self) -> None:
        """`{server}_task` opens a nested ReAct loop and keeps its longer bound."""
        from src.core.constants import MCP_ITERATIVE_TASK_SUFFIX
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout(
            f"mcp_user_770baa3e{MCP_ITERATIVE_TASK_SUFFIX}", None
        ) == pytest.approx(float(settings.mcp_react_step_timeout_seconds))

    def test_a_native_tool_is_unaffected(self) -> None:
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout("get_emails_tool", None) == pytest.approx(
            float(settings.default_tool_timeout_seconds)
        )


class TestTheBoundIsNeverSubSecond:
    """The message renders the bound with `:.0f`, so a sub-half-second bound
    would tell the model a tool was "stopped after 0s" — an absurd fact it
    would then relay. The policy cannot produce one: every family floor is a
    Settings field with `ge >= 1`. This pins the link, so lowering a bound
    fails here rather than surfacing as a nonsense sentence to the model.
    """

    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_emails_tool",
            "delegate_to_sub_agent_tool",
            "browser_task_tool",
            "mcp_user_abc_get_x",
            "generate_image",
            "some_unlisted_tool",
        ],
    )
    def test_every_family_bound_is_at_least_one_second(self, tool_name: str) -> None:
        from src.domains.agents.orchestration.step_timeouts import compute_step_timeout

        assert compute_step_timeout(tool_name, None) >= 1.0

    def test_the_generic_floor_setting_cannot_go_sub_second(self) -> None:
        from src.core.config.agents import AgentsSettings

        field = AgentsSettings.model_fields["default_tool_timeout_seconds"]
        floor = next(m.ge for m in field.metadata if getattr(m, "ge", None) is not None)

        assert floor >= 1.0, "a sub-second floor would render as 'stopped after 0s'"


class TestTimeoutAttribution:
    """Saying WHICH bound fired, because the wrong number is an invented fact.

    Behavioural now, not a source-string assertion: the wording is a named
    function beside its two siblings (``abandoned_call_message``,
    ``repeated_call_message``), so it can be exercised directly.
    """

    def test_our_own_cut_names_the_budget(self) -> None:
        msg = tool_timeout_message("browser_task_tool", bound_s=300.0, elapsed_s=300.0)

        assert "execution budget" in msg
        assert "300s" in msg

    def test_a_tool_that_gave_up_early_is_not_attributed_to_us(self) -> None:
        """An MCP call hitting its per-server bound at 10 s must not be reported
        as 'stopped after 300 s' — a number the run never reached (ADR-182)."""
        msg = tool_timeout_message("mcp_user_x_get_y", bound_s=300.0, elapsed_s=10.0)

        assert "on its own" in msg
        assert "10s" in msg
        assert "300s" not in msg

    def test_scheduling_jitter_still_counts_as_ours(self) -> None:
        """wait_for wakes a hair late; a hair EARLY must not flip attribution."""
        msg = tool_timeout_message("get_emails_tool", bound_s=30.0, elapsed_s=29.5)

        assert "execution budget" in msg

    def test_both_wordings_say_what_to_do_next(self) -> None:
        """A bare refusal is what a stalled model retries verbatim."""
        for elapsed in (300.0, 1.0):
            msg = tool_timeout_message("t", bound_s=300.0, elapsed_s=elapsed)
            assert "narrower request" in msg
            assert "unavailable" in msg

    def test_the_margin_is_declared_once_and_shared(self) -> None:
        from src.domains.agents.nodes import react_nodes as rn

        assert 0.0 < TIMEOUT_ATTRIBUTION_MARGIN <= 1.0
        # The node reads the same constant it decides its log label with, so the
        # message and the `enforced_by` field can never disagree.
        assert rn.TIMEOUT_ATTRIBUTION_MARGIN is TIMEOUT_ATTRIBUTION_MARGIN

    def test_the_node_delegates_the_wording(self) -> None:
        source = inspect.getsource(react_nodes.react_execute_tools_node)

        assert "tool_timeout_message(" in source
        assert "execution budget" not in source, "the wording must live with its siblings"
