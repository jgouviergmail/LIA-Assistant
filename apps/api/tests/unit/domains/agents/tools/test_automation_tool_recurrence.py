"""What the chat tool turns a spoken schedule into.

This is the transcription seam: the LLM names weekdays and an hour, and the
tool must produce a recurrence the studio, the grid and the scheduler all
read the same way. It had no direct test — the draft tests exercise what
happens AFTER the draft exists.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.recurrence import RecurrenceSpec
from src.domains.agents.tools.automation_tools import create_scheduled_action_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_database() -> Iterator[None]:
    """`@with_user_preferences` queries the user row; a unit test must not.

    Left unpatched the decorator opens a real connection, degrades on failure
    and the test still passes — nine seconds later, and green for the wrong
    reason on a machine with no database at all.
    """
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


async def _create(runtime: MagicMock, **kwargs: object) -> object:
    defaults: dict[str, object] = {
        "title": "Revue de presse",
        "action_prompt": "fais-moi une revue de presse",
        "repeat": "weekly",
        "weekdays": [1, 2, 3, 4, 5],
        "times": ["08:00"],
        "user_timezone": "Europe/Paris",
        "locale": "fr",
    }
    defaults.update(kwargs)
    return await create_scheduled_action_tool.coroutine(  # type: ignore[misc]
        runtime=runtime, **defaults
    )


@contextmanager
def _capture_draft() -> Iterator[dict[str, Any]]:
    """Capture the draft content the tool publishes.

    The tool's OUTPUT carries only the draft id — the content goes to
    `DraftService`. Asserting there is asserting on what the tool produced,
    without a store or a database in a unit test.
    """
    captured: dict[str, Any] = {}

    class _Service:
        def create_draft(self, **kwargs: Any) -> UnifiedToolOutput:
            captured.update(kwargs["content"])
            return UnifiedToolOutput.data_success(message="ok", structured_data={})

    with patch("src.domains.agents.tools.automation_tools.DraftService", _Service):
        yield captured


class TestTheToolProducesAReadableRecurrence:
    """A draft carries a spec every other surface can re-read."""

    @pytest.mark.asyncio
    async def test_weekdays_at_one_time_round_trip(self, _runtime: MagicMock) -> None:
        with _capture_draft() as draft:
            await _create(_runtime)

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.freq == "weekly"
        assert spec.interval == 1
        assert spec.byweekday == (1, 2, 3, 4, 5)
        assert spec.per_day() == 1
        assert spec.times.at[0].hour == 8

    @pytest.mark.asyncio
    async def test_a_model_repeating_a_day_is_repaired_not_refused(
        self, _runtime: MagicMock
    ) -> None:
        """`[1, 1, 3]` is exactly what a model writes when it hesitates.

        It carries no ambiguity about intent, so the spec folds it (ADR-184)
        instead of handing the model an error it cannot act on. Left unfolded,
        the card read "le lundi, lundi et mercredi".
        """
        with _capture_draft() as draft:
            await _create(_runtime, weekdays=[3, 1, 1])

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.byweekday == (1, 3)
        assert "lundi et mercredi" in draft["schedule_human"]

    @pytest.mark.asyncio
    async def test_an_impossible_weekday_is_refused_with_a_relayable_message(
        self, _runtime: MagicMock
    ) -> None:
        """Day 0 is the classic off-by-one of a model counting from zero."""
        result = await _create(_runtime, weekdays=[0])

        assert result.success is False
        assert result.error_code == "invalid_schedule"
        assert "weekday" in result.message

    @pytest.mark.asyncio
    async def test_the_anchor_is_the_user_local_day_not_the_server_day(
        self, _runtime: MagicMock
    ) -> None:
        """The anchor phases the series; reading it in UTC shifts it by a day
        for anyone east of Greenwich late in the evening."""
        from datetime import UTC, datetime

        with (
            patch(
                "src.domains.agents.tools.automation_tools.now_utc",
                return_value=datetime(2026, 3, 9, 23, 30, tzinfo=UTC),
            ),
            _capture_draft() as draft,
        ):
            await _create(_runtime, user_timezone="Asia/Tokyo")

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.anchor_date.isoformat() == "2026-03-10"


class TestTheShapesTheCronColumnsCouldNotSay:
    """What widening the tool actually bought.

    None of these four was expressible before: the signature held a set of
    weekdays, one hour and one minute, so a single occurrence, an interval, a
    day of month and a second time in the same day had no way in.
    """

    @pytest.mark.asyncio
    async def test_twice_in_the_same_day(self, _runtime: MagicMock) -> None:
        with _capture_draft() as draft:
            await _create(_runtime, repeat="daily", weekdays=None, times=["08:00", "18:00"])

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.per_day() == 2

    @pytest.mark.asyncio
    async def test_a_single_occurrence(self, _runtime: MagicMock) -> None:
        with _capture_draft() as draft:
            await _create(
                _runtime,
                repeat="once",
                weekdays=None,
                times=["09:00"],
                starting_on="2099-01-15",
            )

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.freq == "once"
        assert spec.anchor_date.isoformat() == "2099-01-15"

    @pytest.mark.asyncio
    async def test_every_other_week(self, _runtime: MagicMock) -> None:
        with _capture_draft() as draft:
            await _create(_runtime, repeat="weekly", weekdays=[2], times=["09:00"], repeat_every=2)

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.interval == 2

    @pytest.mark.asyncio
    async def test_the_second_tuesday_of_the_month(self, _runtime: MagicMock) -> None:
        with _capture_draft() as draft:
            await _create(
                _runtime, repeat="monthly", weekdays=None, times=["14:00"], nth_weekday="2:2"
            )

        spec = RecurrenceSpec.model_validate(draft["recurrence"])
        assert spec.nth_weekday == (2, 2)


class TestWhatARoutineMayNotAsk:
    """The ceiling travels with the caller, and it is REFUSED, not clamped."""

    @pytest.mark.asyncio
    async def test_more_firings_a_day_than_a_routine_allows(self, _runtime: MagicMock) -> None:
        """Every 5 minutes over 8 hours is 97 firings; a routine gets 12."""
        result = await _create(
            _runtime,
            repeat="daily",
            weekdays=None,
            times=None,
            every_minutes=5,
            window_start="08:00",
            window_end="16:00",
        )

        assert result.success is False
        assert result.error_code == "invalid_schedule"

    @pytest.mark.asyncio
    async def test_a_message_the_model_can_relay(self, _runtime: MagicMock) -> None:
        """Not "invalid schedule": it must name what could not be read."""
        result = await _create(_runtime, repeat="monthly", weekdays=None, times=["08:00"])

        assert result.success is False
        assert "day of month" in result.message


class TestARoutineAnswersAnImpossibleScheduleToo:
    """The same contract as the reminder tool, on the other scheduling path.

    Both tools call the one translation, so both inherit its promise: a
    structural refusal arrives as a `RecurrenceError` and comes back as a
    relayable failure, never as a raised `ValidationError` carrying Pydantic's
    field names (measured 2026-09-06).
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("label", "params"),
        [
            ("the 31st of February", {"repeat": "yearly", "months": [2], "month_days": [31]}),
            ("a weekday of 9", {"repeat": "weekly", "weekdays": [9]}),
            ("a frequency that ignores what was said", {"repeat": "daily", "month_days": [15]}),
        ],
    )
    async def test_it_comes_back_as_a_relayable_failure(
        self, label: str, params: dict[str, object], _runtime: MagicMock
    ) -> None:
        # The file's own helper, so the defaults stay in one place. The
        # default weekdays are cleared unless the case names its own.
        overrides: dict[str, object] = {"weekdays": None, "months": None, "month_days": None}
        overrides.update(params)
        result = await _create(_runtime, **overrides)

        assert result.success is False  # type: ignore[attr-defined]
        assert result.error_code == "invalid_schedule"  # type: ignore[attr-defined]
        message = result.message or ""  # type: ignore[attr-defined]
        assert "errors.pydantic.dev" not in message
        assert message.strip()
