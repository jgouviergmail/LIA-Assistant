"""The scheduled-action contract, on the recurrence spec.

Range checks on days, hours and minutes are NOT repeated here: the vocabulary
owns them (`tests/unit/core/recurrence/test_spec.py`), and a second copy would
be a second authority on what a recurrence may say. What this file pins is what
the CONTRACT adds — the routine cap, an update that leaves the schedule alone,
and the fields the response derives.
"""

from datetime import UTC, date, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.exceptions import ValidationError as DomainValidationError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.schemas import (
    ConditionConfig,
    ScheduledActionCreate,
    ScheduledActionResponse,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import validate_routine_creation
from tests.helpers.routine_caps import pin_routine_caps


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

    def test_a_recurrence_beyond_the_routine_cap_is_refused_at_creation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A routine runs an agent pipeline on every occurrence: its ceiling is
        lower than a reminder's by default, and it is INJECTED, never owned by
        the recurrence model — enforced where a routine is CREATED, so a stored
        one stays readable when the operator lowers the caps."""
        pin_routine_caps(monkeypatch)
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
        new = ScheduledActionCreate(title="t", action_prompt="p", recurrence=dense)
        with pytest.raises(DomainValidationError):
            validate_routine_creation(new, "Europe/Paris")


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

    def test_a_new_recurrence_beyond_the_cap_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_routine_caps(monkeypatch)
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


def _response(recurrence: RecurrenceSpec | None, **over: object) -> ScheduledActionResponse:
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
        "notify_only_when_new": False,
        "execution_mode": "react",
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
    return ScheduledActionResponse.model_validate(base)


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
        assert created.notify_only_when_new is False

    def test_a_routine_may_ask_to_be_told_only_of_something_new(self):
        from src.domains.scheduled_actions.schemas import ScheduledActionCreate

        created = ScheduledActionCreate(**self._base(notify_only_when_new=True))
        assert created.notify_only_when_new is True

    def test_it_cannot_also_propose_first(self):
        """A proposal IS a notification: there would be nothing to hold back."""
        import pytest as _pytest
        from pydantic import ValidationError as _ValidationError

        from src.domains.scheduled_actions.schemas import ScheduledActionCreate

        with _pytest.raises(_ValidationError, match="notify_only_when_new"):
            ScheduledActionCreate(**self._base(notify_only_when_new=True, requires_approval=True))

    def test_an_update_leaves_the_option_alone_or_sets_it_never_nulls_it(self):
        """The column holds a boolean: an explicit null would reach it as one."""
        import pytest as _pytest
        from pydantic import ValidationError as _ValidationError

        from src.domains.scheduled_actions.schemas import ScheduledActionUpdate

        assert ScheduledActionUpdate().model_dump(exclude_unset=True) == {}
        assert ScheduledActionUpdate(notify_only_when_new=False).notify_only_when_new is False
        with _pytest.raises(_ValidationError, match="notify_only_when_new"):
            ScheduledActionUpdate(notify_only_when_new=None)

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


class TestOneClockPerRoutine:
    """ADR-322: a schedule, or a condition the system checks — never both."""

    def _base(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {"title": "Routine", "action_prompt": "fais un point"}
        data.update(overrides)
        return data

    def test_a_condition_routine_needs_no_schedule(self) -> None:
        created = ScheduledActionCreate(
            **self._base(
                trigger_kind="condition",
                condition_config=ConditionConfig(type="mail_match", query="devis"),
            )
        )

        assert created.recurrence is None

    def test_a_condition_routine_refuses_a_schedule(self) -> None:
        with pytest.raises(ValidationError, match="no recurrence"):
            ScheduledActionCreate(
                **self._base(
                    recurrence=weekly((9, 0)),
                    trigger_kind="condition",
                    condition_config=ConditionConfig(type="task_overdue"),
                )
            )

    def test_a_scheduled_routine_still_needs_its_schedule(self) -> None:
        with pytest.raises(ValidationError, match="recurrence is required"):
            ScheduledActionCreate(**self._base())


class TestASignedCallIsTheThirdClock:
    """ADR-386: a routine another system starts has neither schedule nor condition."""

    def _base(self, **overrides: object) -> dict[str, object]:
        data: dict[str, object] = {
            "title": "Door",
            "action_prompt": "tell me who rang",
            "trigger_kind": "webhook",
        }
        data.update(overrides)
        return data

    def test_it_needs_neither_a_schedule_nor_a_condition(self) -> None:
        created = ScheduledActionCreate(**self._base())

        assert created.recurrence is None and created.condition_config is None

    def test_it_refuses_a_schedule(self) -> None:
        with pytest.raises(ValidationError, match="runs when its address is called"):
            ScheduledActionCreate(**self._base(recurrence=weekly((9, 0))))

    def test_it_refuses_a_condition(self) -> None:
        with pytest.raises(ValidationError, match="runs when its address is called"):
            ScheduledActionCreate(
                **self._base(condition_config=ConditionConfig(type="task_overdue"))
            )

    def test_it_cannot_propose_first(self) -> None:
        # A proposal hands the run to the chat, which would never read the
        # calls the routine was started for.
        with pytest.raises(ValidationError, match="cannot propose first"):
            ScheduledActionCreate(**self._base(requires_approval=True))

    def test_it_may_ask_to_be_told_only_of_something_new(self) -> None:
        created = ScheduledActionCreate(**self._base(notify_only_when_new=True))

        assert created.notify_only_when_new is True


class TestTheLastWatchedDay:
    def test_every_condition_type_may_stop_on_a_day(self) -> None:
        config = ConditionConfig(type="task_overdue", until=date(2026, 10, 12))

        # Stored as JSON: a date object in a JSONB column fails at flush.
        assert config.stored() == {"type": "task_overdue", "until": "2026-10-12"}

    def test_an_unreadable_day_is_refused_at_the_door(self) -> None:
        with pytest.raises(ValidationError):
            ConditionConfig.model_validate({"type": "task_overdue", "until": "someday"})


class TestTheWeatherKinds:
    def test_the_kinds_are_stored_in_one_order_whatever_the_order_sent(self) -> None:
        # Ticking « snow » then « rain » is the condition « rain » then « snow »:
        # another order must not read as another condition, whose ledger would
        # start over and announce the same forecast again.
        one = ConditionConfig(type="weather_change", kinds=["snow", "rain", "rain"])
        two = ConditionConfig(type="weather_change", kinds=["rain", "snow"])

        assert one.stored() == two.stored() == {"type": "weather_change", "kinds": ["rain", "snow"]}


class TestAParameterItsTypeDoesNotRead:
    """Accepted, stored, displayed and DROPPED — refused instead (ADR-268's rule)."""

    @pytest.mark.parametrize(
        ("config", "stray"),
        [
            ({"type": "task_overdue", "query": "facture"}, "query"),
            ({"type": "mail_match", "query": "devis", "kinds": ["rain"]}, "kinds"),
            ({"type": "document_added", "within_hours": 3}, "within_hours"),
            ({"type": "weather_change", "query": "pluie"}, "query"),
        ],
    )
    def test_it_is_refused(self, config: dict[str, object], stray: str) -> None:
        with pytest.raises(ValidationError, match=stray):
            ConditionConfig.model_validate(config)

    def test_what_a_type_reads_is_accepted(self) -> None:
        config = ConditionConfig(type="calendar_event", query="dentiste", within_hours=6)

        assert config.stored() == {"type": "calendar_event", "query": "dentiste", "within_hours": 6}


class TestAWatchedPage:
    """ADR-387: a page a person watches — its address, and the lines that matter."""

    def test_it_reads_an_address_and_an_optional_filter(self) -> None:
        config = ConditionConfig(
            type="page_change", url="  https://shop.example.com/p/42?ref=a  ", contains="€"
        )

        assert config.stored() == {
            "type": "page_change",
            "url": "https://shop.example.com/p/42?ref=a",
            "contains": "€",
        }
        assert ConditionConfig(type="page_change", url="http://example.org/").url == (
            "http://example.org/"
        )

    def test_it_needs_its_address(self) -> None:
        with pytest.raises(ValidationError, match="page_change requires a url"):
            ConditionConfig(type="page_change")

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.org/file",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://",
            "example.org/no-scheme",
            "https://user:secret@example.org/",
            "https://localhost/admin",
            "https://printer.local/",
            "http://127.0.0.1:8000/",
            "http://10.0.0.5/",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/",
        ],
    )
    def test_an_address_no_public_page_has_is_refused_at_the_door(self, url: str) -> None:
        # The message is matched whole: Pydantic's own text quotes the input,
        # and a bare « url » would match a refusal of anything else.
        with pytest.raises(ValidationError, match="url refused: "):
            ConditionConfig(type="page_change", url=url)

    @pytest.mark.parametrize(
        ("config", "stray"),
        [
            ({"type": "mail_match", "query": "devis", "url": "https://example.org/"}, "url"),
            ({"type": "task_overdue", "contains": "€"}, "contains"),
            ({"type": "page_change", "url": "https://example.org/", "query": "prix"}, "query"),
        ],
    )
    def test_a_parameter_another_type_reads_is_refused(
        self, config: dict[str, object], stray: str
    ) -> None:
        with pytest.raises(ValidationError, match=f"{stray} does not apply to"):
            ConditionConfig.model_validate(config)

    def test_its_bound_is_the_one_the_schema_publishes(self) -> None:
        from src.core.constants import PAGE_WATCH_URL_MAX_CHARS

        published = ConditionConfig.model_json_schema()["properties"]["url"]
        assert any(
            branch.get("maxLength") == PAGE_WATCH_URL_MAX_CHARS
            for branch in published.get("anyOf", [published])
        )
        too_long = "https://example.org/" + "a" * PAGE_WATCH_URL_MAX_CHARS
        with pytest.raises(ValidationError, match=f"at most {PAGE_WATCH_URL_MAX_CHARS} characters"):
            ConditionConfig(type="page_change", url=too_long)

    def test_a_blank_filter_is_refused_like_an_empty_one(self) -> None:
        with pytest.raises(ValidationError, match="contains is blank"):
            ConditionConfig(type="page_change", url="https://example.org/", contains="   ")

    def test_an_empty_filter_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="at least 1 character"):
            ConditionConfig(type="page_change", url="https://example.org/", contains="")


class TestAConditionRoutineResponse:
    """The card, the hub and the chat read the system's clock, not a schedule."""

    def _condition(self, **over: object) -> ScheduledActionResponse:
        base: dict[str, object] = {
            "trigger_kind": "condition",
            "condition_config": {"type": "task_overdue", "until": "2026-10-12"},
            "condition_state": {
                "seen": ["k1"],
                "last_checked_at": "2026-09-25T12:10:00+00:00",
                "last_check_error": "unavailable",
            },
        }
        base.update(over)
        return _response(None, **base)

    def test_it_states_its_check_cadence_and_last_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "scheduled_actions_condition_check_minutes", 10)
        with patch("src.domains.scheduled_actions.schemas.resolve_language", return_value="en"):
            response = self._condition()

        assert response.schedule_display == "Checked about every 10 min, until 12/10/2026"
        assert response.check_interval_minutes == 10

    def test_it_carries_its_last_check_and_never_its_facts(self) -> None:
        response = self._condition()

        assert response.last_checked_at == datetime(2026, 9, 25, 12, 10, tzinfo=UTC)
        assert response.last_check_error == "unavailable"
        assert "condition_state" not in response.model_dump()
        assert "seen" not in response.model_dump_json()

    def test_it_has_no_schedule_to_show(self) -> None:
        response = self._condition()

        assert response.recurrence is None
        assert response.next_occurrences == []
        assert response.times_of_day == []
        assert response.week_slots == []
        assert response.runs_per_day == 0

    def test_a_scheduled_routine_has_no_check_clock(self) -> None:
        response = _response(weekly((8, 0)))

        assert response.check_interval_minutes is None
        assert response.last_checked_at is None


class TestTheListPublishesTheClock:
    def test_the_cadence_of_every_type_and_the_daily_cap_are_published(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.scheduled_actions.models import CONDITION_TYPES
        from src.domains.scheduled_actions.schemas import ScheduledActionListResponse

        monkeypatch.setattr(settings, "scheduled_actions_weather_check_minutes", 60)
        monkeypatch.setattr(settings, "scheduled_actions_condition_max_fires_per_day", 7)

        listing = ScheduledActionListResponse(scheduled_actions=[], total=0)

        assert set(listing.condition_check_minutes) == set(CONDITION_TYPES)
        assert listing.condition_check_minutes["weather_change"] == 60
        assert listing.condition_max_fires_per_day == 7

    def test_the_weather_rule_is_published_as_the_executor_applies_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The studio states when a weather routine fires BEFORE it is saved:
        # the horizon, the strict threshold and the one source (ADR-184).
        from src.core.config import settings
        from src.domains.scheduled_actions.schemas import ScheduledActionListResponse

        monkeypatch.setattr(settings, "scheduled_actions_weather_horizon_hours", 3)
        monkeypatch.setattr(settings, "scheduled_actions_weather_min_precipitation_percent", 65)

        rule = ScheduledActionListResponse(scheduled_actions=[], total=0).weather_condition_rule

        assert rule.model_dump() == {
            "horizon_hours": 3,
            "min_precipitation_percent": 65,
            "source": "google_weather",
        }
