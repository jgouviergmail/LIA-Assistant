"""No wall clock around a model call reads anything but its slot (ADR-221 amendment).

admin-llm-config displays a timeout per model. It is the one the call gets: a
constant or an environment value that cuts the call earlier makes the screen lie,
which is how a document configured at 300 s came to be cut at 120 s.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.core.config import settings
from src.core.constants import LLM_RUN_BOUND_MARGIN_SECONDS
from src.domains.agents.orchestration.step_timeouts import TOOL_LLM_SLOTS
from src.domains.agents.utils.react_budget import (
    react_compute_budget_seconds,
    react_exit_reason,
)
from src.domains.journals.consolidation_lifecycle import consolidation_bound_seconds
from src.domains.world.message_attempts import ATTEMPT_SECONDS, attempt_seconds
from src.infrastructure.proactive.discussion_bounds import (
    discussion_deadline_seconds,
    discussion_lease_seconds,
)
from src.infrastructure.scheduler.heartbeat_wake_sweep import _serve_bound_seconds
from src.infrastructure.scheduler.out_of_turn_run import unattended_turn_seconds
from src.infrastructure.scheduler.scheduled_action_executor import (
    _attempt_bound_seconds as routine_attempt_seconds,
)
from src.infrastructure.scheduler.workboard_runner import (
    _attempt_bound_seconds as ticket_attempt_seconds,
)

SRC = Path(__file__).resolve().parents[2] / "src"

#: What sends a request to a model.
MODEL_DOORS = frozenset(
    {
        "get_structured_output",
        "get_structured_output_with_retry",
        "invoke_with_instrumentation",
        "ainvoke",
        "astream",
    }
)
#: Every slot one turn may call, whichever its mode.
TURN_SLOTS = ("query_analyzer", "react_agent", "planner", "response")
#: What a bound around a model call may read.
SLOT_DOORS = frozenset(
    {
        "llm_call_timeout_seconds",
        "run_bound_seconds",
        "compute_step_timeout",
        "consolidation_bound_seconds",
    }
)
#: A tool module that reaches a model, its slots declared elsewhere.
DECLARED_ELSEWHERE = {
    # A server's task is named after the server: `_MCP_TASK_LLM_SLOTS` covers them all.
    "mcp_react_tools.py",
    # The base class of the three nested loops, each declared under its own tool.
    "react_runner.py",
    # Imports the delivery sweep to kick it: the model is called by the sweep, not the tool.
    "peers_tools.py",
    # The one reply writer of two tools, each declared under its own name (ADR-383).
    "reply_writing.py",
}


def _sources() -> Iterator[Path]:
    """The application's modules; a hidden folder holds a tool's leftovers."""
    for path in SRC.rglob("*.py"):
        if not any(part.startswith(".") for part in path.relative_to(SRC).parts):
            yield path


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return call.func.id if isinstance(call.func, ast.Name) else ""


def _calls(node: ast.AST) -> Iterator[ast.Call]:
    return (child for child in ast.walk(node) if isinstance(child, ast.Call))


def _reads_a_slot(bound: ast.expr, scope: ast.AST, functions: dict[str, ast.AST]) -> bool:
    """Whether a bound is read through a slot door, directly or one name away."""
    for call in _calls(bound):
        name = _call_name(call)
        if name in SLOT_DOORS:
            return True
        helper = functions.get(name)
        if helper is not None and any(_call_name(c) in SLOT_DOORS for c in _calls(helper)):
            return True
    names = {
        node.attr if isinstance(node, ast.Attribute) else node.id
        for node in ast.walk(bound)
        if isinstance(node, ast.Name | ast.Attribute)
    }
    for assignment in ast.walk(scope):
        if not isinstance(assignment, ast.Assign):
            continue
        targets = {
            target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            for target in assignment.targets
        }
        if targets & names and any(_call_name(c) in SLOT_DOORS for c in _calls(assignment.value)):
            return True
    return False


def wall_clocks_off_the_slot(source: str) -> list[int]:
    """The lines of every wall clock around a model call that reads no slot.

    Args:
        source: A module's text.

    Returns:
        The offending lines; a call is followed one name away, inside its module.
    """
    tree = ast.parse(source)
    functions: dict[str, ast.AST] = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    def reaches_a_model(node: ast.AST) -> bool:
        for call in _calls(node):
            name = _call_name(call)
            if name in MODEL_DOORS:
                return True
            target = functions.get(name)
            if target is not None and any(_call_name(c) in MODEL_DOORS for c in _calls(target)):
                return True
        return False

    offenders: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == "wait_for" and node.args:
            keyword = next((k.value for k in node.keywords if k.arg == "timeout"), None)
            bound = keyword if keyword is not None else node.args[-1]
            if reaches_a_model(node.args[0]) and not _reads_a_slot(bound, tree, functions):
                offenders.append(node.lineno)
        if isinstance(node, ast.AsyncWith):
            for item in node.items:
                context = item.context_expr
                if not (isinstance(context, ast.Call) and _call_name(context) == "timeout"):
                    continue
                body = ast.Module(body=node.body, type_ignores=[])
                if (
                    context.args
                    and reaches_a_model(body)
                    and not _reads_a_slot(context.args[0], tree, functions)
                ):
                    offenders.append(node.lineno)
    return offenders


@pytest.mark.unit
class TestTheGuardBites:
    """A guard that runs for no case guards nothing: each shape it must refuse."""

    @pytest.mark.parametrize(
        "source",
        [
            "async def f(llm):\n    await asyncio.wait_for(llm.ainvoke(x), timeout=30)\n",
            "async def f(llm):\n    await asyncio.wait_for(llm.ainvoke(x), settings.t)\n",
            "async def f(llm):\n    async with asyncio.timeout(8):\n"
            "        await llm.ainvoke(x)\n",
            "async def g(llm):\n    await get_structured_output(llm)\n"
            "async def f(llm):\n    await asyncio.wait_for(g(llm), timeout=SOME_CONSTANT)\n",
        ],
    )
    def test_a_foreign_bound_is_refused(self, source: str) -> None:
        assert wall_clocks_off_the_slot(source)

    @pytest.mark.parametrize(
        "source",
        [
            "async def f(llm):\n"
            "    await asyncio.wait_for(llm.ainvoke(x), timeout=llm_call_timeout_seconds('a'))\n",
            "def b():\n    return run_bound_seconds(1.0, 'a')\n"
            "async def f(llm):\n    await asyncio.wait_for(llm.ainvoke(x), timeout=b())\n",
            "class C:\n"
            "    def __init__(self):\n"
            "        self._t = t or llm_call_timeout_seconds('a')\n"
            "    async def f(self, llm):\n"
            "        await asyncio.wait_for(llm.ainvoke(x), timeout=self._t)\n",
            "async def f():\n    await asyncio.wait_for(read(), timeout=30)\n",
        ],
    )
    def test_the_slot_and_the_unrelated_pass(self, source: str) -> None:
        assert wall_clocks_off_the_slot(source) == []


@pytest.mark.unit
class TestEveryWallClockReadsItsSlot:
    def test_no_wall_clock_around_a_model_reads_a_foreign_bound(self) -> None:
        offenders = {
            str(path.relative_to(SRC)): lines
            for path in _sources()
            if (lines := wall_clocks_off_the_slot(path.read_text(encoding="utf-8")))
        }
        assert offenders == {}

    def test_the_walk_met_the_clocks_it_exists_for(self) -> None:
        """A scan that finds nothing would pass: it must see a known wall clock."""
        known = SRC / "domains/agents/services/query_analyzer_service.py"
        tree = ast.parse(known.read_text(encoding="utf-8"))

        assert any(_call_name(call) == "wait_for" for call in _calls(tree))


@pytest.mark.unit
class TestEveryToolReachingAModelDeclaresItsSlots:
    @staticmethod
    def _modules_calling_a_model() -> set[str]:
        found: set[str] = set()
        for path in _sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(_call_name(call) in {"get_llm", *MODEL_DOORS} for call in _calls(tree)):
                relative = path.relative_to(SRC.parent).with_suffix("")
                found.add(".".join(relative.parts))
        return found

    def test_a_tool_module_importing_a_model_call_lists_a_tool(self) -> None:
        """A net at module level: a new tool beside a declared one is the author's to add."""
        calling = self._modules_calling_a_model()
        declared = {name.removesuffix("_tool") for name in TOOL_LLM_SLOTS}
        undeclared: list[str] = []
        for path in sorted((SRC / "domains/agents/tools").glob("*.py")):
            if path.name in DECLARED_ELSEWHERE:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            reached = imported & calling
            tools = {
                node.name.removesuffix("_tool")
                for node in ast.walk(tree)
                if isinstance(node, ast.AsyncFunctionDef)
            }
            if reached and not tools & declared:
                undeclared.append(path.name)

        assert undeclared == []


@pytest.fixture
def slots() -> Iterator[dict[str, dict[str, Any]]]:
    """Rows of ``llm_config_overrides``, as the in-memory cache serves them."""
    rows: dict[str, dict[str, Any]] = {}
    with patch(
        "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
        side_effect=rows.get,
    ):
        yield rows


@pytest.mark.unit
class TestRunsYieldToTheirSlots:
    def test_a_react_call_longer_than_the_budget_does_not_spend_it(
        self, slots: dict[str, Any]
    ) -> None:
        """One call the slot allows must not end the loop by itself."""
        allowed = settings.react_agent_timeout_seconds * 2
        slots["react_agent"] = {"timeout_seconds": allowed}

        assert react_exit_reason({"react_elapsed_seconds": allowed - 1.0}) is None
        assert react_exit_reason({"react_elapsed_seconds": allowed + 1000.0}) == "compute_budget"

    def test_a_short_react_slot_leaves_the_budget_to_the_environment(
        self, slots: dict[str, Any]
    ) -> None:
        slots["react_agent"] = {"timeout_seconds": 1}

        assert react_compute_budget_seconds() == settings.react_agent_timeout_seconds

    def test_a_consolidation_waits_for_its_call(self, slots: dict[str, Any]) -> None:
        allowed = settings.journal_consolidation_timeout_seconds * 2
        slots["journal_consolidation"] = {"timeout_seconds": allowed}

        assert consolidation_bound_seconds() == allowed + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_an_opening_run_waits_for_its_three_calls(self, slots: dict[str, Any]) -> None:
        for slot in ("discussion_context", "discussion_decision", "discussion_message"):
            slots[slot] = {"timeout_seconds": 1000}

        assert discussion_deadline_seconds(False) == 3000 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_a_rebuild_waits_for_its_context_call(self, slots: dict[str, Any]) -> None:
        slots["discussion_context"] = {
            "timeout_seconds": settings.discussion_rebuild_deadline_seconds * 2
        }

        assert (
            discussion_deadline_seconds(True)
            == settings.discussion_rebuild_deadline_seconds * 2 + LLM_RUN_BOUND_MARGIN_SECONDS
        )

    def test_a_claim_outlives_the_longest_call_it_covers(self, slots: dict[str, Any]) -> None:
        slots["discussion_context"] = {"timeout_seconds": 3000}

        assert discussion_lease_seconds() > 3000

    def test_a_claim_keeps_the_environment_s_lease_for_short_calls(
        self, slots: dict[str, Any]
    ) -> None:
        for slot in ("discussion_context", "discussion_decision", "discussion_message"):
            slots[slot] = {"timeout_seconds": 1}

        assert discussion_lease_seconds() == settings.discussion_run_lease_seconds

    def test_a_wake_waits_for_the_calls_of_a_heartbeat(self, slots: dict[str, Any]) -> None:
        for slot in ("heartbeat_decision", "interest_content", "heartbeat_message"):
            slots[slot] = {"timeout_seconds": 1000}

        assert _serve_bound_seconds() == 3000 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_a_translation_attempt_outlives_its_call(self, slots: dict[str, Any]) -> None:
        slots["world_message_translator"] = {"timeout_seconds": 60}

        assert attempt_seconds() > 60

    def test_a_short_translation_keeps_the_fence(self, slots: dict[str, Any]) -> None:
        slots["world_message_translator"] = {"timeout_seconds": 1}

        assert attempt_seconds() == ATTEMPT_SECONDS

    @pytest.mark.parametrize("loop", ["react_agent", "planner"])
    def test_a_turn_nobody_watches_waits_for_its_calls_in_either_mode(
        self, slots: dict[str, Any], loop: str
    ) -> None:
        """Whoever frees a stranded claim cannot know the mode: both read the longer one."""
        for slot in TURN_SLOTS:
            slots[slot] = {"timeout_seconds": 1}
        slots[loop] = {"timeout_seconds": 1000}

        assert unattended_turn_seconds(1) == 1002 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_short_calls_leave_the_turn_to_the_environment(self, slots: dict[str, Any]) -> None:
        for slot in TURN_SLOTS:
            slots[slot] = {"timeout_seconds": 1}

        assert unattended_turn_seconds(1000) == 1000

    def test_a_turn_s_bound_is_whole_seconds_rounded_up(self, slots: dict[str, Any]) -> None:
        """A slot is a float, the bound a number the failure message prints."""
        for slot in TURN_SLOTS:
            slots[slot] = {"timeout_seconds": 1000.25}

        bound = unattended_turn_seconds(1)

        assert isinstance(bound, int)
        assert bound == 3001 + LLM_RUN_BOUND_MARGIN_SECONDS

    def test_a_routine_and_a_ticket_yield_to_the_slots(self, slots: dict[str, Any]) -> None:
        slots["react_agent"] = {"timeout_seconds": 100000}

        assert routine_attempt_seconds() > 100000
        assert ticket_attempt_seconds() > 100000

    def test_a_routine_and_a_ticket_keep_their_own_budget(self, slots: dict[str, Any]) -> None:
        for slot in TURN_SLOTS:
            slots[slot] = {"timeout_seconds": 1}

        assert routine_attempt_seconds() == settings.scheduled_actions_execution_timeout_seconds
        assert ticket_attempt_seconds() == settings.workboard_run_timeout_seconds
