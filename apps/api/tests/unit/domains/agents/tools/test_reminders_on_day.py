"""The reminders of one day, for a plan that asks « do I have a reminder that day? ».

ADR-390 qualification (2026-11-15, E08): « what is the ticket's deadline, and do I
have a reminder that day? ». The reminder tool took no day, so the plan listed every
pending reminder and left the response to compare the dates — and it answered « no
reminder that day » above the very reminder of that day, on both draws. The loop,
comparing in its own reasoning, answered right. A plan chains a value it read
(``$steps.step_1.tickets[0].due_at``) into a parameter: the tool now has one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.agents.reminders.catalogue_manifests import list_reminders_catalogue_manifest
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.reminder_tools import list_reminders_tool
from src.domains.reminders.models import Reminder, ReminderStatus
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")


async def _list(rows: list[Reminder], **arguments: str) -> tuple[UnifiedToolOutput, AsyncMock]:
    runtime = make_tool_runtime(
        user_id=uuid4(), thread_id=str(uuid4()), side_channel_queue=object(), store=MagicMock()
    )

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncMock]:
        yield AsyncMock()

    listed = AsyncMock(return_value=rows)
    with (
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.domains.reminders.service.ReminderService") as service,
        patch("src.domains.agents.application.authorization.load_actor", AsyncMock()),
        patch("src.domains.agents.application.availability.require_application_tools", AsyncMock()),
        patch(
            "src.domains.agents.tools.runtime_helpers.get_user_preferences",
            AsyncMock(return_value=("Europe/Paris", "fr", "fr")),
        ),
    ):
        service.return_value.list_pending_for_user = listed
        assert list_reminders_tool.coroutine is not None
        result = await list_reminders_tool.coroutine(
            runtime=runtime, user_timezone="Europe/Paris", locale="fr", **arguments
        )
    assert isinstance(result, UnifiedToolOutput)
    return result, listed


async def test_a_deadline_s_instant_reads_the_reminders_of_its_local_day() -> None:
    _result, listed = await _list([], on_day="2026-11-17T17:00:00+00:00")

    assert listed.await_args.kwargs["fires_between"] == (
        datetime(2026, 11, 17, tzinfo=PARIS),
        datetime(2026, 11, 18, tzinfo=PARIS),
    )


async def test_without_a_day_every_pending_reminder_is_read() -> None:
    _result, listed = await _list([])

    assert listed.await_args.kwargs["fires_between"] is None


async def test_a_day_with_no_reminder_says_which_day() -> None:
    result, _listed = await _list([], on_day="2026-11-17")

    assert result.success
    assert result.structured_data == {"reminders": [], "on_day": "2026-11-17"}


async def test_a_value_it_cannot_read_is_refused_never_replaced() -> None:
    """ADR-310: a tool never falls back in silence on a value it cannot read."""
    result, listed = await _list([], on_day="le jour de l'échéance")

    assert not result.success
    assert result.error_code == "INVALID_INPUT"
    assert "not readable" in result.message
    listed.assert_not_awaited()


async def test_a_reminder_of_that_day_is_listed() -> None:
    row = Reminder(
        id=uuid4(),
        user_id=uuid4(),
        content="Rapporter les livres à la médiathèque",
        original_message="Rapporter les livres à la médiathèque",
        recurrence=RecurrenceSpec.model_validate(
            {
                "freq": "once",
                "anchor_date": "2026-11-17",
                "times": {"at": [{"hour": 10, "minute": 0}]},
            }
        ).model_dump(mode="json"),
        trigger_at=datetime(2026, 11, 17, 9, tzinfo=UTC),
        user_timezone=PARIS.key,
        status=ReminderStatus.PENDING.value,
        retry_count=0,
        created_at=datetime(2026, 11, 15, tzinfo=UTC),
        updated_at=datetime(2026, 11, 15, tzinfo=UTC),
    )

    result, _listed = await _list([row], on_day="2026-11-17")

    assert result.success
    assert "Rapporter les livres" in str(result.registry_updates)


def test_a_span_of_several_days_is_not_split_into_day_calls() -> None:
    """Measured 2026-11-15 (E05): « my reminders of the next three days » became one
    call per day, today and the two following, and the reminder three days ahead was
    never read; the soonest-first page lets the answer read the span whole."""
    declared = next(p for p in list_reminders_catalogue_manifest.parameters if p.name == "on_day")

    assert "ONE day" in declared.description
    assert "several days" in declared.description


def test_the_planner_and_the_loop_read_one_wording() -> None:
    """The loop binds the ``@tool`` schema, never the manifest (ADR-310)."""
    declared = next(p for p in list_reminders_catalogue_manifest.parameters if p.name == "on_day")
    bound = list_reminders_tool.args_schema.model_fields["on_day"].description

    assert declared.description == bound
    assert declared.semantic_type == "datetime"
    assert not declared.required
