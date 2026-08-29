"""The ephemeral-script tool: what it refuses, and what it publishes.

The capability is a COMPLEMENT, never an obligation: the agent reaches for it
when a task needs computation a language model is bad at — combining records,
arithmetic over many rows, durations across timezones, deduplication — and
ignores it otherwise.

Four refusals carry the design, and each has a reason that is not stylistic:

1. **outside ReAct** — the pipeline is deterministic and plans ahead; it uses
   skills and plugins (owner arbitration). A planner that emitted this step
   would run model-authored code outside the loop that can read its traceback
   and repair it;
2. **flag off** — one emergency switch, for the self-hoster;
3. **budget spent** — a prompt-injected loop must not be able to spin the host;
4. **legacy sandbox** — enforced one layer down, in the executor.

And one publication: every bound the tool enforces is stated in its manifest
and its description (ADR-184), including the fact that there is NO network and
which libraries exist — otherwise the model spends an iteration discovering it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT

pytestmark = [pytest.mark.unit]


def _runtime(mode: str = EXECUTION_MODE_REACT) -> SimpleNamespace:
    context = SimpleNamespace(
        user_id=uuid4(),
        thread_id="t1",
        conversation_id="c1",
        execution_mode=mode,
    )
    return SimpleNamespace(context=context)


def _ok(stdout: str = "3\n") -> SimpleNamespace:
    return SimpleNamespace(success=True, output=stdout, error=None)


async def _call(code: str = "print(1+2)", **kwargs: Any) -> Any:
    from src.domains.agents.tools.python_sandbox_tools import run_python_tool

    return await run_python_tool.coroutine(
        code=code,
        purpose=kwargs.pop("purpose", "sum the durations"),
        runtime=kwargs.pop("runtime", _runtime()),
        **kwargs,
    )


class TestItRefusesOutsideReact:
    async def test_the_pipeline_never_runs_model_authored_code(self) -> None:
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
        ) as executor:
            result = await _call(runtime=_runtime(EXECUTION_MODE_PIPELINE))

        assert result.success is False
        executor.assert_not_awaited()

    async def test_the_manifest_declares_the_restriction(self) -> None:
        """The planner must not even be offered the tool."""
        from src.domains.agents.python_sandbox.catalogue_manifests import (
            run_python_catalogue_manifest,
        )

        assert run_python_catalogue_manifest.execution_modes == frozenset({EXECUTION_MODE_REACT})


class TestItRefusesWhenSwitchedOff:
    async def test_the_flag_gates_the_capability(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "python_sandbox_tool_enabled", False, raising=False)
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
        ) as executor:
            result = await _call()

        assert result.success is False
        executor.assert_not_awaited()


class TestTheTurnBudgetIsBounded:
    async def test_a_run_beyond_the_per_turn_cap_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.agents.tools import python_sandbox_tools

        monkeypatch.setattr(settings, "python_sandbox_max_runs_per_turn", 2, raising=False)
        python_sandbox_tools.reset_turn_budget()

        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok(),
        ) as executor:
            first = await _call()
            second = await _call()
            third = await _call()

        assert first.success is True and second.success is True
        assert third.success is False, "the third run exceeds the turn budget"
        assert executor.await_count == 2, "a refused run never reaches the sandbox"

    async def test_a_new_turn_starts_with_a_fresh_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.agents.tools import python_sandbox_tools

        monkeypatch.setattr(settings, "python_sandbox_max_runs_per_turn", 1, raising=False)
        python_sandbox_tools.reset_turn_budget()

        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok(),
        ):
            assert (await _call()).success is True
            assert (await _call()).success is False
            python_sandbox_tools.reset_turn_budget()
            assert (await _call()).success is True


class TestTheTurnsDataIsHandedOver:
    async def test_the_turn_registry_reaches_the_script_on_stdin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The model references collected data instead of re-typing it."""
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        python_sandbox_tools.set_turn_data(
            {"e1": {"type": "EMAIL", "subject": "Vol retour"}},
        )

        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok(),
        ) as executor:
            await _call()

        payload = executor.await_args.kwargs["payload"]
        assert payload["items"]["e1"]["subject"] == "Vol retour"

    async def test_an_empty_registry_still_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        python_sandbox_tools.set_turn_data({})

        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok(),
        ) as executor:
            result = await _call()

        assert result.success is True
        assert executor.await_args.kwargs["payload"]["items"] == {}


class TestWhatComesBack:
    async def test_stdout_is_returned_and_marked_untrusted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Model-authored code over third-party data — the output is DATA."""
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok("total: 3h40\n"),
        ):
            result = await _call()

        assert result.success is True
        blob = json.dumps(result.model_dump(), default=str)
        assert "3h40" in blob
        assert "untrusted" in blob.lower()

    async def test_a_traceback_comes_back_so_the_model_can_repair(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        failure = SimpleNamespace(
            success=False, output="", error="NameError: name 'total' is not defined"
        )
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=failure,
        ):
            result = await _call()

        assert result.success is False
        assert "NameError" in json.dumps(result.model_dump(), default=str)


class TestTheContractIsPublished:
    """What the tool enforces, the model must be able to read (ADR-184)."""

    def test_the_description_states_the_hard_facts(self) -> None:
        from src.domains.agents.python_sandbox.catalogue_manifests import (
            run_python_catalogue_manifest,
        )

        description = run_python_catalogue_manifest.description.lower()
        assert "no network" in description or "aucun réseau" in description
        assert "numpy" in description, "the available libraries must be listed"
        assert "stdin" in description, "the data channel must be explained"

    def test_it_says_when_not_to_use_it(self) -> None:
        from src.domains.agents.python_sandbox.catalogue_manifests import (
            run_python_catalogue_manifest,
        )

        assert "do not use" in run_python_catalogue_manifest.description.lower()


class TestTheLoopWiresIt:
    """A budget nobody resets, or data nobody publishes, protects nothing."""

    def test_the_setup_resets_the_turn_budget(self) -> None:
        import inspect

        from src.domains.agents.nodes import react_nodes

        assert "reset_turn_budget()" in inspect.getsource(react_nodes.react_setup_node)

    def test_the_execute_node_publishes_the_turn_data(self) -> None:
        import inspect

        from src.domains.agents.nodes import react_nodes

        assert "set_turn_data(" in inspect.getsource(react_nodes.react_execute_tools_node)


class TestTheAdminSeesTheCode:
    """The code is admin-facing ONLY (owner arbitration): debug panel, not answer."""

    async def test_each_run_is_recorded_for_the_debug_panel(self) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=_ok("7\n"),
        ):
            await _call(code="print(3+4)", purpose="add the legs")

        recorded = python_sandbox_tools.drain_turn_scripts()
        assert len(recorded) == 1
        assert recorded[0]["code"] == "print(3+4)"
        assert recorded[0]["purpose"] == "add the legs"
        assert recorded[0]["success"] is True
        assert "7" in recorded[0]["output_head"]

    async def test_a_failed_run_is_recorded_too(self) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.reset_turn_budget()
        failure = SimpleNamespace(success=False, output="", error="ZeroDivisionError")
        with patch(
            "src.domains.skills.executor.SkillScriptExecutor.execute_source",
            new_callable=AsyncMock,
            return_value=failure,
        ):
            await _call(code="print(1/0)", purpose="divide")

        recorded = python_sandbox_tools.drain_turn_scripts()
        assert recorded[0]["success"] is False
        assert "ZeroDivisionError" in recorded[0]["output_head"]

    def test_the_state_key_is_declared(self) -> None:
        """An undeclared key is dropped silently by LangGraph (systemic rule)."""
        from src.domains.agents.models import MessagesState

        assert "react_scripts" in MessagesState.__annotations__

    def test_the_debug_stage_publishes_them(self) -> None:
        import inspect

        from src.domains.agents.services.streaming import debug_metrics_stages

        source = inspect.getsource(debug_metrics_stages.build_react_execution)
        assert '"scripts"' in source
