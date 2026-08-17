"""UnifiedToolOutput failures must not be reported as executor successes.

Measured in prod (2026-08-17, request 2ecc670c): ``send_peer_message_tool``
refused a 6,149-char relay ("The message exceeds 2000 characters.",
INVALID_INPUT) — no draft, no ``peer_messages`` row — yet the step was logged
``success: true`` and the answer told the user the message had been delivered
("Message transmis … contenu intégral"). Root cause: the
``StandardToolOutput | UnifiedToolOutput`` branch of ``_execute_tool``
hardcoded ``{"success": True}`` instead of reading ``result.success``.

The false success also disarmed the ADR-184 honesty layer: a step whose
outcome dict says ``success is not False`` counts as *executed* in
``plan_blockers.executed_tool_names``, which silences the validator's
CONSTRAINT_VIOLATION blocker as stale.

Contract pinned here:
- ``UnifiedToolOutput.failure`` → executor result ``success=False`` with
  ``error`` and ``error_code`` propagated (and thus excluded from
  ``executed_tool_names``).
- ``UnifiedToolOutput.data_success`` / ``action_success`` → ``success=True``
  unchanged, registry updates preserved.
- Legacy ``StandardToolOutput`` (no ``success`` field) → implicit success,
  behavior unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.field_names import FIELD_ERROR_CODE
from src.domains.agents.orchestration import parallel_executor as pe
from src.domains.agents.tools.output import StandardToolOutput, UnifiedToolOutput

_FAILURE_MESSAGE = "The message exceeds 2000 characters."


def _fake_tool(coroutine: Any) -> SimpleNamespace:
    """Minimal StructuredTool stand-in: _execute_tool only needs .coroutine."""
    return SimpleNamespace(coroutine=coroutine, args_schema=None, name="fake_tool")


def _registry_returning(tool: Any) -> MagicMock:
    registry = MagicMock()
    registry.get_tool.return_value = tool
    return registry


async def _run_execute_tool(output: Any) -> pe.ToolExecutionResult:
    """Run _execute_tool against a stub tool returning the given output."""

    async def _coroutine(**kwargs: Any) -> Any:
        return output

    tool = _fake_tool(_coroutine)
    with (
        patch.object(pe.ToolRegistry, "get_instance", return_value=_registry_returning(tool)),
        patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
    ):
        return await pe._execute_tool(
            tool_name="fake_tool",
            args={},
            config={"configurable": {}},
            store=None,
        )


@pytest.mark.unit
@pytest.mark.asyncio
class TestUnifiedOutputFailurePropagation:
    """A typed tool failure must surface as a failed executor result."""

    async def test_failure_output_is_not_a_success(self) -> None:
        result = await _run_execute_tool(
            UnifiedToolOutput.failure(message=_FAILURE_MESSAGE, error_code="INVALID_INPUT")
        )

        assert result.result["success"] is False

    async def test_failure_output_propagates_error_and_code(self) -> None:
        result = await _run_execute_tool(
            UnifiedToolOutput.failure(message=_FAILURE_MESSAGE, error_code="INVALID_INPUT")
        )

        assert result.result["error"] == _FAILURE_MESSAGE
        assert result.result[FIELD_ERROR_CODE] == "INVALID_INPUT"

    async def test_failure_output_keeps_message_for_response_llm(self) -> None:
        """The failure text stays readable by the response node (honest answer)."""
        result = await _run_execute_tool(
            UnifiedToolOutput.failure(message=_FAILURE_MESSAGE, error_code="INVALID_INPUT")
        )

        assert result.result["message"] == _FAILURE_MESSAGE

    async def test_failure_step_is_excluded_from_executed_tool_names(self) -> None:
        """ADR-184: a failed step must not silence the validator's blocker."""
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )
        from src.domains.agents.services.plan_blockers import executed_tool_names

        result = await _run_execute_tool(
            UnifiedToolOutput.failure(message=_FAILURE_MESSAGE, error_code="INVALID_INPUT")
        )

        plan = ExecutionPlan(
            plan_id="plan_test",
            user_id="00000000-0000-0000-0000-000000000001",
            steps=[
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    tool_name="send_peer_message_tool",
                    agent_name="peer_agent",
                    description="relay",
                    parameters={},
                )
            ],
        )

        executed = executed_tool_names(plan, {"step_2": result.result})

        assert "send_peer_message_tool" not in executed


@pytest.mark.unit
@pytest.mark.asyncio
class TestUnifiedOutputSuccessUnchanged:
    """Success outputs keep their historical executor contract."""

    async def test_data_success_stays_success_with_registry(self) -> None:
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
        )

        item = RegistryItem(
            id="contact_abc",
            type=RegistryItemType.CONTACT,
            payload={"name": "Hua"},
            meta=RegistryItemMeta(source="test", domain="contacts"),
        )
        result = await _run_execute_tool(
            UnifiedToolOutput.data_success(
                message="Found 1 contact",
                registry_updates={"contact_abc": item},
            )
        )

        assert result.result["success"] is True
        assert "contact_abc" in result.registry_updates

    async def test_action_success_stays_success(self) -> None:
        result = await _run_execute_tool(
            UnifiedToolOutput.action_success(message="Reminder created")
        )

        assert result.result["success"] is True
        assert result.result["message"] == "Reminder created"

    async def test_legacy_standard_output_keeps_implicit_success(self) -> None:
        """StandardToolOutput has no success field — implicit success preserved.

        Also pins the latent crash found while writing this suite: the branch
        read ``result.context_save_mode``, which StandardToolOutput does not
        define — any legacy output would have raised AttributeError and been
        converted into a failed step.
        """
        result = await _run_execute_tool(StandardToolOutput(summary_for_llm="Found 3 contacts"))

        assert result.result["success"] is True
        assert result.result["message"] == "Found 3 contacts"


@pytest.mark.unit
@pytest.mark.asyncio
class TestStepResultErrorCodeTolerance:
    """Tool error codes outside the ToolErrorCode enum must not crash the step.

    Tools emit free-form codes through ``UnifiedToolOutput.failure`` (measured
    in-tree: TOOL_ERROR, VALIDATION_ERROR, RATE_LIMITED, FEATURE_DISABLED…).
    ``StepResult.error_code`` is typed ``ToolErrorCode | None`` — a non-member
    code degrades to ``None`` there while the raw string stays visible in the
    result dict for the response LLM and the logs.
    """

    async def _run_step_with_error_code(self, error_code: str) -> Any:
        from src.domains.agents.orchestration.parallel_executor import (
            _execute_tool_step,
        )
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionStep,
            StepType,
        )

        step = ExecutionStep(
            step_id="step_1",
            step_type=StepType.TOOL,
            tool_name="fake_tool",
            agent_name="peer_agent",
            description="fake",
            parameters={},
        )
        tool_result = pe.ToolExecutionResult(
            result={
                "success": False,
                "error": _FAILURE_MESSAGE,
                FIELD_ERROR_CODE: error_code,
                "message": _FAILURE_MESSAGE,
            }
        )
        with (
            patch.object(pe, "_get_tool_manifest_for_step", return_value=(None, None)),
            patch.object(pe, "_execute_tool", new=AsyncMock(return_value=tool_result)),
        ):
            return await _execute_tool_step(
                step=step,
                completed_steps={},
                config={"configurable": {}},
                wave_id=0,
                store=None,
            )

    async def test_enum_member_code_is_typed(self) -> None:
        from src.domains.agents.tools.common import ToolErrorCode

        result = await self._run_step_with_error_code("INVALID_INPUT")

        assert result.success is False
        assert result.error_code == ToolErrorCode.INVALID_INPUT

    async def test_non_member_code_degrades_without_crash(self) -> None:
        result = await self._run_step_with_error_code("RATE_LIMITED")

        assert result.success is False
        assert result.error_code is None
        assert result.result[FIELD_ERROR_CODE] == "RATE_LIMITED"
        assert result.error == _FAILURE_MESSAGE
