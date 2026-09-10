"""Which mode an out-of-turn run executes in, and who decides (2026-09-09).

``stream_chat_response`` defaults its ``user_execution_mode`` to « pipeline »,
and no out-of-turn caller passed one: every routine and every ticket ran the
planner whatever the person had chosen for their chat. Now the CALLER decides,
and nothing reads the chat preference — a routine keeps the deterministic
pipeline it has always run on, a ticket asks for the autonomous loop, and the
header's toggle keeps meaning the chat alone.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import settings
from src.infrastructure.scheduler.out_of_turn_run import StreamRequest, _one_attempt

pytestmark = pytest.mark.unit


def _request(**overrides: Any) -> StreamRequest:
    base: dict[str, Any] = {
        "user_id": uuid.uuid4(),
        "prompt": "Réserver la salle",
        "session_id": "s",
        "language": "fr",
        "timezone": "Europe/Paris",
        "display_name": "Jérôme",
        "display_mode": "cards",
        "timeout_seconds": 30,
        "max_attempts": 1,
        "retry_delay_seconds": 0,
    }
    base.update(overrides)
    return StreamRequest(**base)


async def _capture_call(request: StreamRequest) -> dict[str, Any]:
    """Run one attempt against a stubbed service and return its kwargs."""
    seen: dict[str, Any] = {}

    async def stream(**kwargs: Any) -> Any:
        seen.update(kwargs)
        yield SimpleNamespace(type="token", content="ok")

    service = MagicMock()
    service.stream_chat_response = MagicMock(side_effect=stream)
    with patch("src.domains.agents.api.service.AgentService", return_value=service):
        await _one_attempt(request, 1)
    return seen


class TestTheCallerDecidesTheMode:
    async def test_a_request_saying_nothing_runs_the_pipeline(self) -> None:
        """The routine path builds its request without a mode: it must keep
        the deterministic planner it has always run on."""
        seen = await _capture_call(_request())

        assert seen["user_execution_mode"] == "pipeline"

    async def test_a_request_asking_for_the_loop_gets_it(self) -> None:
        seen = await _capture_call(_request(execution_mode="react"))

        assert seen["user_execution_mode"] == "react"

    async def test_the_mode_is_passed_EXPLICITLY_never_defaulted(self) -> None:
        """The parameter's own default is « pipeline »: an omission would look
        exactly like a decision, which is how every run ignored the mode."""
        seen = await _capture_call(_request(execution_mode="react"))

        assert "user_execution_mode" in seen


class TestTheRowDecides:
    """2026-09-09: the mode belongs to the ROW, not to the deployment.

    A ticket and a routine each carry their own — react by default, because
    nobody is there to steer a plan — and the person changes it whenever they
    like. A deployment switch could not say that two tickets of one account
    want different modes; the chat's header toggle still speaks for the chat
    alone, and neither path may read it.
    """

    def test_a_new_row_is_born_in_the_loop(self) -> None:
        from src.core.constants import OUT_OF_TURN_EXECUTION_MODE_DEFAULT

        assert OUT_OF_TURN_EXECUTION_MODE_DEFAULT == "react"

    def test_both_tables_carry_it_not_null(self) -> None:
        from src.domains.scheduled_actions.models import ScheduledAction
        from src.domains.workboard.models import WorkboardTicket

        for model in (WorkboardTicket, ScheduledAction):
            column = model.__table__.c.execution_mode
            assert column.nullable is False, model.__tablename__
            assert column.server_default is not None, model.__tablename__

    @pytest.mark.parametrize(
        ("module", "expression"),
        [
            ("src/infrastructure/scheduler/workboard_runner.py", "execution_mode=prepared."),
            (
                "src/infrastructure/scheduler/scheduled_action_executor.py",
                "execution_mode=action.execution_mode",
            ),
        ],
    )
    def test_each_runner_passes_its_own_rows_mode(self, module: str, expression: str) -> None:
        """Read from the source: a caller that forgets it inherits the
        service's « pipeline » default in silence — which is exactly how
        routines ran the planner for a year."""
        from pathlib import Path

        source = Path(module).read_text(encoding="utf-8")

        assert expression in source
        assert "user.execution_mode" not in source
        assert "holder.execution_mode" not in source

    def test_no_deployment_switch_survives(self) -> None:
        """The setting it replaced: dead the moment the row decides, and dead
        code is deleted rather than left for a reader to wonder about."""
        assert not hasattr(settings, "workboard_run_execution_mode")
