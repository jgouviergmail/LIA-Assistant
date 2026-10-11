"""A launch receipt never claims the background instruction has completed."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from redis.exceptions import RedisError

from src.core.i18n_application import APPLICATION_ROUTINE_RUN
from src.domains.agents.application.routine_execution import _run_reserved
from src.domains.agents.application.routine_execution_policy import RoutineExecutionReservation
from src.domains.agents.application.routine_schemas import RoutineSnapshot
from src.domains.agents.services.draft_execution_result import DraftExecutionResult
from src.domains.agents.tools.application_routine_tools import execute_lia_routine_tool

pytestmark = pytest.mark.unit


def test_manual_tool_cannot_accept_an_instruction_or_account_from_the_model() -> None:
    validator = Draft202012Validator(execute_lia_routine_tool.tool_call_schema.model_json_schema())
    selection = {"routine_id": str(uuid4())}
    assert validator.is_valid({"selection": selection})
    assert not validator.is_valid(
        {"selection": {**selection, "action_prompt": "Different instruction"}}
    )
    assert not validator.is_valid({"selection": {**selection, "actor_id": str(uuid4())}})
    assert "runtime" not in execute_lia_routine_tool.tool_call_schema.model_fields


@pytest.mark.parametrize("language", list(APPLICATION_ROUTINE_RUN))
def test_launch_receipt_uses_an_explicit_recorded_request_message(language: str) -> None:
    result = DraftExecutionResult(
        success=True,
        draft_id="run",
        draft_type="application_action",
        action="confirm",
        result_data={"values": {"launch_reserved": True, "execution_completed": False}},
        user_language=language,
    )
    assert (
        result.to_agent_result()["message"] == APPLICATION_ROUTINE_RUN[result.user_language].title
    )


@pytest.mark.parametrize("ready", [True, False, "redis_error"])
async def test_deferred_launcher_never_calls_the_source_before_chat_readiness(
    ready: bool | str,
) -> None:
    expected = RoutineSnapshot(id=uuid4(), title="Run", enabled=True, configuration_digest="a" * 64)
    reservation = RoutineExecutionReservation(
        uuid4(), expected, uuid4(), datetime.now(UTC) + timedelta(minutes=1)
    )
    wait = AsyncMock(
        side_effect=RedisError("unavailable") if ready == "redis_error" else None,
        return_value=ready is True,
    )
    with (
        patch("src.domains.agents.application.routine_execution.get_redis_cache", AsyncMock()),
        patch("src.domains.agents.application.routine_execution.wait_for_routine_turn", wait),
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.execute_single_action",
            AsyncMock(),
        ) as execute,
        patch(
            "src.domains.agents.application.routine_execution.cancel_routine_reservation",
            AsyncMock(),
        ) as cancel,
    ):
        await _run_reserved(reservation, "owned-conversation")
    assert execute.await_count == int(ready is True)
    cancel.assert_awaited_once_with(reservation)
    if ready is True:
        arguments = execute.await_args.kwargs
        assert (
            arguments["user_id"] == reservation.actor_id and arguments["action_id"] == expected.id
        )
        assert callable(arguments["execution_guard"])
