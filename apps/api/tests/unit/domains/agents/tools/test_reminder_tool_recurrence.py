"""A reminder created by conversation still works, and now carries a schedule.

The tool's signature is unchanged: it speaks `trigger_datetime` and
`relative_trigger`, as it did before reminders could repeat. What changed is
underneath — the service derives a `once` recurrence from the instant, by the
same rule the migration applied to every existing row.

That is the regression this file guards. Teaching the tool to say "every
morning" is the transcription lot, with its own corpus of formulations; doing
it here without one would be guessing at what a model produces.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.recurrence import rearm_after
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.reminder_tools import create_reminder_tool
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_database() -> Iterator[None]:
    """`@with_user_preferences` queries the user row; a unit test must not."""
    with patch(
        "src.domains.agents.tools.runtime_helpers.get_user_preferences",
        AsyncMock(return_value=("Europe/Paris", "fr", "fr")),
    ):
        yield


@pytest.fixture
def _runtime() -> MagicMock:
    return make_tool_runtime(
        user_id=uuid4(),
        thread_id=str(uuid4()),
        side_channel_queue=object(),
        store=MagicMock(),
    )


@contextmanager
def _capture_created() -> Iterator[dict[str, Any]]:
    """Capture what the tool asks the SERVICE to store.

    The tool returns a draft id; the row is built one layer down. Asserting
    there is asserting on what the reminder will actually be, with no database
    in a unit test.
    """
    captured: dict[str, Any] = {}

    class _Service:
        def __init__(self, db: Any) -> None:  # noqa: D107 - test double
            pass

        async def create_reminder(self, user_id: Any, data: Any, user_timezone: str) -> Any:
            captured["data"] = data
            captured["timezone"] = user_timezone
            return MagicMock(
                id=uuid4(),
                content=data.content,
                trigger_at=datetime(2099, 1, 15, 9, 0, tzinfo=UTC),
            )

    class _Session:
        async def __aenter__(self) -> Any:
            # The tool commits its own session: a bare MagicMock returns a
            # MagicMock from `commit()` and `await` on it explodes, which the
            # tool then reports as a creation failure (F028's cousin).
            session = MagicMock()
            session.commit = AsyncMock()
            return session

        async def __aexit__(self, *_: Any) -> bool:
            return False

    with (
        patch("src.domains.reminders.service.ReminderService", _Service),
        patch("src.infrastructure.database.session.get_db_context", lambda: _Session()),
    ):
        yield captured


class TestAReminderFromChatStillWorks:
    @pytest.mark.asyncio
    async def test_it_produces_a_draft_and_no_error(self, _runtime: MagicMock) -> None:
        with _capture_created() as created:
            result = await create_reminder_tool.coroutine(  # type: ignore[misc]
                content="appeler le medecin",
                original_message="rappelle-moi d'appeler le medecin demain a 9h",
                runtime=_runtime,
                trigger_datetime="2099-01-15T09:00:00",
                user_timezone="Europe/Paris",
                locale="fr",
            )

        assert isinstance(result, UnifiedToolOutput)
        assert result.success is True
        # The tool still speaks instants; the SERVICE derives the schedule.
        assert created["data"].recurrence is None

    @pytest.mark.asyncio
    async def test_an_impossible_datetime_is_relayed_not_crashed(self, _runtime: MagicMock) -> None:
        result = await create_reminder_tool.coroutine(  # type: ignore[misc]
            content="x",
            original_message="x",
            runtime=_runtime,
            trigger_datetime="pas une date",
            user_timezone="Europe/Paris",
            locale="fr",
        )

        assert result.success is False


class TestTheDerivedScheduleIsAPostIt:
    """What the service stores for a reminder the tool created.

    Not asserted through the tool (its draft is confirmed later, by another
    path) but through the rule both share: a `once` recurrence built from the
    instant, which arms nothing after it fires.
    """

    def test_the_service_derives_once_from_the_instant(self) -> None:
        from src.domains.reminders.service import once_at

        instant = datetime(2099, 1, 15, 8, 0, tzinfo=UTC)  # 09:00 in Paris
        spec = once_at(instant, "Europe/Paris")

        assert spec.freq == "once"
        assert spec.anchor_date.isoformat() == "2099-01-15"
        assert (spec.times.at[0].hour, spec.times.at[0].minute) == (9, 0)

    def test_that_schedule_deletes_the_reminder_after_it_fires(self) -> None:
        from src.domains.reminders.service import once_at

        instant = datetime(2099, 1, 15, 8, 0, tzinfo=UTC)
        spec = once_at(instant, "Europe/Paris")

        assert rearm_after(spec, "Europe/Paris", due_at=instant, now=instant) is None


class TestTheManifestStillMatchesTheSignature:
    """ADR-184: whatever a validator can reject, its producer must be able to
    read. A parameter added to the tool and not to the manifest is a dead end
    the planner will invent."""

    def test_every_manifest_parameter_exists_on_the_tool(self) -> None:
        import inspect

        from src.domains.agents.reminders.catalogue_manifests import (
            create_reminder_catalogue_manifest as manifest,
        )

        signature = inspect.signature(create_reminder_tool.coroutine)  # type: ignore[arg-type]
        declared = {p.name for p in manifest.parameters}
        assert declared <= set(signature.parameters), declared - set(signature.parameters)

    def test_the_tool_declares_the_recurrence_vocabulary(self) -> None:
        """The transcription lot taught it to say "every morning"."""
        import inspect

        from src.domains.agents.registry.recurrence_parameters import RECURRENCE_DOCS

        signature = inspect.signature(create_reminder_tool.coroutine)  # type: ignore[arg-type]
        assert set(RECURRENCE_DOCS) <= set(signature.parameters)


class TestASpokenScheduleIsConfirmedAsASchedule:
    """What the reader hears back must match what they said.

    Naming only the next instant of a repeating reminder reads as a one-off:
    someone who said "every morning at 8" and is told "set for tomorrow 08:00"
    has no sign the rest was understood.
    """

    @pytest.mark.asyncio
    async def test_a_recurring_reminder_is_confirmed_with_its_schedule(
        self, _runtime: MagicMock
    ) -> None:
        with _capture_created() as created:
            result = await create_reminder_tool.coroutine(  # type: ignore[misc]
                content="prendre les vitamines",
                original_message="rappelle-moi de prendre mes vitamines tous les matins a 8h",
                runtime=_runtime,
                repeat="daily",
                times=["08:00"],
                user_timezone="Europe/Paris",
                locale="fr",
            )

        assert result.success is True
        assert created["data"].recurrence is not None
        # The schedule, not the next instant.
        assert "Tous les jours" in result.message
        assert result.structured_data["schedule_human"]

    @pytest.mark.asyncio
    async def test_a_single_instant_keeps_the_wording_it_always_had(
        self, _runtime: MagicMock
    ) -> None:
        with _capture_created():
            result = await create_reminder_tool.coroutine(  # type: ignore[misc]
                content="appeler le medecin",
                original_message="rappelle-moi d'appeler le medecin demain a 9h",
                runtime=_runtime,
                trigger_datetime="2099-01-15T09:00:00",
                user_timezone="Europe/Paris",
                locale="fr",
            )

        assert result.success is True
        assert result.structured_data["schedule_human"] is None

    @pytest.mark.asyncio
    async def test_two_ways_of_saying_when_are_refused(self, _runtime: MagicMock) -> None:
        """They can disagree; the reminder would announce one and arrive at
        the other. The API layer refuses the same pair for the same reason."""
        result = await create_reminder_tool.coroutine(  # type: ignore[misc]
            content="x",
            original_message="x",
            runtime=_runtime,
            trigger_datetime="2099-01-15T09:00:00",
            repeat="daily",
            times=["08:00"],
            user_timezone="Europe/Paris",
            locale="fr",
        )

        assert result.success is False
        assert result.error_code == "invalid_parameters"

    @pytest.mark.asyncio
    async def test_a_schedule_beyond_what_a_reminder_allows_is_refused(
        self, _runtime: MagicMock
    ) -> None:
        """Every minute over eight hours is 481 firings; a reminder gets 48."""
        result = await create_reminder_tool.coroutine(  # type: ignore[misc]
            content="x",
            original_message="x",
            runtime=_runtime,
            repeat="daily",
            every_minutes=1,
            window_start="08:00",
            window_end="16:00",
            user_timezone="Europe/Paris",
            locale="fr",
        )

        assert result.success is False
        assert result.error_code == "invalid_schedule"


class TestAnImpossibleScheduleIsAnswered:
    """The tool ANSWERS a refusal; it never raises one.

    Measured 2026-09-06: the structural refusals are raised inside Pydantic
    validators and reached this layer wrapped in `ValidationError`, which the
    tool's `except RecurrenceError` did not catch. The tool raised, and the
    message that would have been relayed carried Pydantic's field names and a
    documentation URL — the two things an error payload returned to a model
    must never contain.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("label", "params"),
        [
            ("the 31st of February", {"repeat": "yearly", "months": [2], "month_days": [31]}),
            ("a single day with an interval", {"repeat": "once", "repeat_every": 2}),
            ("a weekday of 9", {"repeat": "weekly", "weekdays": [9]}),
            ("a month of 13", {"repeat": "yearly", "months": [13], "month_days": [1]}),
            (
                "a frequency that ignores what was said",
                {"repeat": "weekly", "weekdays": [1], "month_days": [15]},
            ),
        ],
    )
    async def test_it_comes_back_as_a_relayable_failure(
        self, label: str, params: dict[str, object], _runtime: MagicMock
    ) -> None:
        result = await create_reminder_tool.coroutine(  # type: ignore[misc]
            content="x",
            original_message="x",
            runtime=_runtime,
            times=["08:00"],
            user_timezone="Europe/Paris",
            locale="fr",
            **params,
        )

        assert result.success is False
        assert result.error_code == "invalid_schedule"
        assert "errors.pydantic.dev" not in (result.message or "")
        assert "Traceback" not in (result.message or "")
        assert (result.message or "").strip()

    @pytest.mark.asyncio
    async def test_a_plausible_rewording_is_repaired_and_the_answer_says_so(
        self, _runtime: MagicMock
    ) -> None:
        """ "Every weekday at 8" must not become "every day", silently."""
        with _capture_created() as created:
            result = await create_reminder_tool.coroutine(  # type: ignore[misc]
                content="x",
                original_message="x",
                runtime=_runtime,
                repeat="daily",
                weekdays=[1, 2, 3, 4, 5],
                times=["08:00"],
                user_timezone="Europe/Paris",
                locale="fr",
            )

        assert result.success is True
        # What is STORED is the weekly rule the reader meant...
        stored = created["data"].recurrence
        assert stored is not None
        assert stored.freq == "weekly"
        assert stored.byweekday == (1, 2, 3, 4, 5)
        # ...and what the reader is TOLD says so, rather than "every day".
        assert result.structured_data is not None
        assert result.structured_data["schedule_human"] == "En semaine, à 08:00"
