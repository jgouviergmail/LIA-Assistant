"""The scheduled-action contract, on the recurrence spec.

Range checks on days, hours and minutes are NOT repeated here: the vocabulary
owns them (`tests/unit/core/recurrence/test_spec.py`), and a second copy would
be a second authority on what a recurrence may say. What this file pins is what
the CONTRACT adds — the routine cap, an update that leaves the schedule alone,
and the fields the response derives.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.schemas import (
    ConditionConfig,
    ScheduledActionCreate,
    ScheduledActionResponse,
    ScheduledActionUpdate,
)


def at(*pairs: tuple[int, int]) -> DailyTimes:
    return DailyTimes(mode="at", at=tuple(TimeOfDay(hour=h, minute=m) for h, m in pairs))


def weekly(*pairs: tuple[int, int]) -> RecurrenceSpec:
    """A weekly routine anchored in the PAST, so it is running this week.

    An anchor in the future is legitimate — the series simply has not started —
    but it makes a week-slot assertion test the anchor rather than the week.
    """
    return RecurrenceSpec(
        freq="weekly",
        times=at(*pairs),
        anchor_date=date(2026, 1, 5),
        byweekday=(1, 2, 3, 4, 5),
    )


class TestScheduledActionCreate:
    """What a routine may be created with."""

    def test_valid_create(self) -> None:
        data = ScheduledActionCreate(
            title="Revue de presse", action_prompt="fais-moi une revue", recurrence=weekly((8, 0))
        )
        assert data.recurrence.freq == "weekly"
        assert data.recurrence.byweekday == (1, 2, 3, 4, 5)

    def test_several_moments_a_day_are_accepted(self) -> None:
        data = ScheduledActionCreate(
            title="t", action_prompt="p", recurrence=weekly((8, 0), (12, 30), (19, 0))
        )
        assert data.recurrence.per_day() == 3

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledActionCreate(title="", action_prompt="p", recurrence=weekly((8, 0)))

    def test_empty_prompt_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledActionCreate(title="t", action_prompt="", recurrence=weekly((8, 0)))

    def test_title_max_length(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledActionCreate(title="x" * 201, action_prompt="p", recurrence=weekly((8, 0)))

    def test_a_recurrence_beyond_the_routine_cap_is_refused(self) -> None:
        """A routine runs an agent pipeline on every occurrence: its ceiling is
        lower than a reminder's, and it is INJECTED, never owned by the
        recurrence model."""
        dense = RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="every",
                step_minutes=30,
                start=TimeOfDay(hour=0, minute=0),
                end=TimeOfDay(hour=23, minute=30),
            ),
            anchor_date=date(2026, 9, 7),
        )
        with pytest.raises(ValidationError):
            ScheduledActionCreate(title="t", action_prompt="p", recurrence=dense)


class TestScheduledActionUpdate:
    """What an update may change, and what it leaves alone."""

    def test_all_none(self) -> None:
        update = ScheduledActionUpdate()
        assert update.model_dump(exclude_unset=True) == {}

    def test_partial_update_title(self) -> None:
        update = ScheduledActionUpdate(title="new")
        assert update.model_dump(exclude_unset=True) == {"title": "new"}

    def test_an_absent_recurrence_leaves_the_schedule_alone(self) -> None:
        update = ScheduledActionUpdate(title="new")
        assert "recurrence" not in update.model_dump(exclude_unset=True)

    def test_a_new_recurrence_travels(self) -> None:
        update = ScheduledActionUpdate(recurrence=weekly((7, 15)))
        assert update.recurrence is not None
        assert update.recurrence.times.materialise()[0].hour == 7

    def test_a_new_recurrence_beyond_the_cap_is_refused(self) -> None:
        dense = RecurrenceSpec(
            freq="daily",
            times=DailyTimes(
                mode="every",
                step_minutes=30,
                start=TimeOfDay(hour=0, minute=0),
                end=TimeOfDay(hour=23, minute=30),
            ),
            anchor_date=date(2026, 9, 7),
        )
        with pytest.raises(ValidationError):
            ScheduledActionUpdate(recurrence=dense)


def _response(recurrence: RecurrenceSpec, **over: object) -> ScheduledActionResponse:
    """A response built from the fields the ORM supplies."""
    base: dict[str, object] = {
        "id": uuid4(),
        "user_id": uuid4(),
        "title": "t",
        "action_prompt": "p",
        "recurrence": recurrence,
        "user_timezone": "Europe/Paris",
        "trigger_kind": "time",
        "condition_config": None,
        "requires_approval": False,
        "next_trigger_at": datetime(2026, 9, 8, 6, 0, tzinfo=UTC),
        "is_enabled": True,
        "status": "active",
        "last_executed_at": None,
        "execution_count": 0,
        "consecutive_failures": 0,
        "last_error": None,
        "created_at": datetime(2026, 9, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    base.update(over)
    return ScheduledActionResponse(**base)  # type: ignore[arg-type]


class TestScheduledActionResponse:
    """The derived fields — computed server-side, never in the browser."""

    def test_the_moments_of_a_day_are_materialised_here(self) -> None:
        """The browser never expands a `mode: "every"` step itself: it would be
        a second reading of the schedule, and the two would disagree at the
        daylight-saving edges."""
        response = _response(
            RecurrenceSpec(
                freq="daily",
                times=DailyTimes(
                    mode="every",
                    step_minutes=120,
                    start=TimeOfDay(hour=8, minute=0),
                    end=TimeOfDay(hour=14, minute=0),
                ),
                anchor_date=date(2026, 9, 7),
            )
        )
        assert response.times_of_day == ["08:00", "10:00", "12:00", "14:00"]
        assert response.runs_per_day == 4

    def test_the_sentence_and_the_next_runs_are_filled(self) -> None:
        response = _response(weekly((8, 0)))
        assert response.schedule_display
        assert response.next_occurrences

    def test_a_finished_series_carries_a_null_trigger(self) -> None:
        response = _response(
            RecurrenceSpec(freq="once", times=at((9, 0)), anchor_date=date(2026, 1, 1)),
            next_trigger_at=None,
        )
        assert response.next_trigger_at is None
        assert response.next_occurrences == []


class TestConditionConfig:
    """N-07: per-type validation at the API boundary."""

    def test_accepts_each_known_type(self):

        assert ConditionConfig(type="task_overdue").type == "task_overdue"
        assert ConditionConfig(type="weather_change", kinds=["rain"]).kinds == ["rain"]
        assert ConditionConfig(type="mail_match", query="facture").query == "facture"
        assert ConditionConfig(type="document_added").type == "document_added"
        assert ConditionConfig(type="calendar_event", within_hours=2).within_hours == 2

    def test_rejects_unknown_type_and_kinds(self):
        import pytest as _pytest

        with _pytest.raises(ValueError):
            ConditionConfig(type="moon_phase")
        with _pytest.raises(ValueError):
            ConditionConfig(type="weather_change", kinds=["lava"])

    def test_mail_match_requires_query_and_within_hours_is_calendar_only(self):
        import pytest as _pytest

        with _pytest.raises(ValueError):
            ConditionConfig(type="mail_match")
        with _pytest.raises(ValueError):
            ConditionConfig(type="task_overdue", within_hours=2)


class TestCreateConditionCoherence:
    """N-07: kind/config pairing enforced on create; time stays the default."""

    def _base(self, **overrides):
        data = {
            "title": "Routine",
            "action_prompt": "fais un point",
            "recurrence": weekly((9, 0)),
        }
        data.update(overrides)
        return data

    def test_defaults_keep_the_historical_time_behavior(self):
        from src.domains.scheduled_actions.models import TriggerKind
        from src.domains.scheduled_actions.schemas import ScheduledActionCreate

        created = ScheduledActionCreate(**self._base())
        assert created.trigger_kind is TriggerKind.TIME
        assert created.condition_config is None
        assert created.requires_approval is False

    def test_condition_kind_requires_a_config(self):
        import pytest as _pytest

        from src.domains.scheduled_actions.schemas import ScheduledActionCreate

        with _pytest.raises(ValueError):
            ScheduledActionCreate(**self._base(trigger_kind="condition"))

    def test_time_kind_refuses_a_config(self):
        import pytest as _pytest

        from src.domains.scheduled_actions.schemas import (
            ScheduledActionCreate,
        )

        with _pytest.raises(ValueError):
            ScheduledActionCreate(
                **self._base(condition_config=ConditionConfig(type="task_overdue"))
            )


class TestTheWeekTravelsWithTheRoutine:
    """The grid must draw from the LISTING, never from a second request.

    Owner arbitration 2026-09-06: an empty grid is a blocking regression. The
    week's instants therefore ride on the routine itself — position is always
    available with the cards — while `/week` keeps carrying the run OUTCOMES,
    whose absence costs a colour, never a chip.
    """

    def test_a_routine_carries_the_instants_of_the_current_week(self) -> None:
        response = _response(weekly((8, 0)))
        assert response.week_slots, "the grid has nothing to draw"
        first = response.week_slots[0]
        assert 1 <= first.day <= 7
        assert (first.hour, first.minute) == (8, 0)

    def test_a_routine_firing_twice_a_day_carries_both_instants(self) -> None:
        response = _response(weekly((8, 0), (18, 0)))
        mondays = [slot for slot in response.week_slots if slot.day == 1]
        assert [(s.hour, s.minute) for s in mondays] == [(8, 0), (18, 0)]

    def test_a_routine_that_fires_no_day_of_this_week_carries_nothing(self) -> None:
        """A monthly routine outside its day draws no chip — and says nothing
        false about the week it is not in."""
        far = RecurrenceSpec(
            freq="yearly",
            times=at((9, 0)),
            anchor_date=date(2026, 1, 1),
            bymonth=(1,),
            bymonthday=(1,),
        )
        assert _response(far).week_slots == []


class TestAnExplicitNullIsNotAnAbsentField:
    """`{"recurrence": null}` is not the same request as omitting the field.

    Omitting it means "leave the schedule alone". Sending null means "set it to
    nothing" — which the column forbids, and which the service would have
    written straight into a NOT NULL column: a 500 where a 422 belongs.
    Found by adversarial review 2026-09-06, not by any test.
    """

    def test_an_explicit_null_recurrence_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            ScheduledActionUpdate.model_validate({"recurrence": None})

    def test_omitting_the_field_still_means_leave_it_alone(self) -> None:
        update = ScheduledActionUpdate.model_validate({"title": "x"})
        assert "recurrence" not in update.model_dump(exclude_unset=True)

    def test_a_real_recurrence_still_travels(self) -> None:
        update = ScheduledActionUpdate.model_validate(
            {"recurrence": weekly((7, 15)).model_dump(mode="json")}
        )
        assert update.recurrence is not None
