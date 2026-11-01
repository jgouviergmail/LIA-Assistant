"""A routine's schedule caps are the operator's settings, read by every door.

« L'intervalle minimum est de 15 minutes » was two constants, and a copy of them
typed into the form: an operator who wanted a routine every five minutes had to
change code in two languages. The caps are now ``SCHEDULED_ACTIONS_MIN_STEP_MINUTES``
and ``SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY`` (ADR-268 amendment 2026-10-30), and the
creation rule, the update schema, the chat tool, its manifest and the list the form
reads all go through ONE reader, ``routine_recurrence_limits`` — so the form, the API
and the agent cannot disagree about what a routine may ask.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.core.config.scheduler import SchedulerSettings
from src.core.constants import (
    RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
    SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_CEILING,
    SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT,
    SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT,
    SCHEDULED_ACTIONS_MIN_STEP_MINUTES_FLOOR,
)
from src.core.exceptions import ValidationError as DomainValidationError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.recurrence_limits import routine_recurrence_limits
from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionListResponse,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import validate_routine_creation
from tests.helpers.routine_caps import pin_routine_caps

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"


def every(
    step: int, *, start: tuple[int, int] = (0, 0), end: tuple[int, int] = (23, 55)
) -> RecurrenceSpec:
    """A daily schedule stepping every ``step`` minutes between two moments."""
    return RecurrenceSpec(
        freq="daily",
        times=DailyTimes(
            mode="every",
            step_minutes=step,
            start=TimeOfDay(hour=start[0], minute=start[1]),
            end=TimeOfDay(hour=end[0], minute=end[1]),
        ),
        anchor_date=date(2026, 10, 30),
    )


class TestTheCapsAreTheOperators:
    def test_the_reader_returns_what_the_settings_say(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_routine_caps(monkeypatch, min_step_minutes=5, max_times_per_day=288)

        limits = routine_recurrence_limits()

        assert limits.min_step_minutes == 5
        assert limits.max_times_per_day == 288
        assert limits.max_series_count == RECURRENCE_ROUTINE_MAX_SERIES_COUNT

    def test_the_settings_default_to_the_caps_production_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Nobody's .env decides this one: both variables removed, no file read.
        monkeypatch.delenv("SCHEDULED_ACTIONS_MIN_STEP_MINUTES", raising=False)
        monkeypatch.delenv("SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY", raising=False)

        defaults = SchedulerSettings(_env_file=None)  # type: ignore[call-arg]

        assert defaults.scheduled_actions_min_step_minutes == (
            SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT
        )
        assert defaults.scheduled_actions_max_times_per_day == (
            SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT
        )

    def test_the_ceiling_is_what_a_day_holds_at_the_floor(self) -> None:
        """Every moment of a day at the shortest step: the per-day cap can say no more."""
        assert SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_CEILING == (
            24 * 60 // SCHEDULED_ACTIONS_MIN_STEP_MINUTES_FLOOR
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("scheduled_actions_min_step_minutes", SCHEDULED_ACTIONS_MIN_STEP_MINUTES_FLOOR - 1),
            ("scheduled_actions_min_step_minutes", 24 * 60 + 1),
            ("scheduled_actions_max_times_per_day", 0),
            (
                "scheduled_actions_max_times_per_day",
                SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_CEILING + 1,
            ),
        ],
    )
    def test_a_cap_outside_its_bounds_refuses_to_boot(self, field: str, value: int) -> None:
        with pytest.raises(ValidationError):
            SchedulerSettings(_env_file=None, **{field: value})  # type: ignore[call-arg]


class TestEveryDoorAppliesTheSameCaps:
    def test_a_five_minute_step_is_refused_under_the_default_caps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Twelve moments in an hour fit the day's cap: only the step is refused."""
        pin_routine_caps(monkeypatch)
        new = ScheduledActionCreate(title="t", action_prompt="p", recurrence=every(5, end=(0, 55)))

        with pytest.raises(
            DomainValidationError,
            match=f"minimum of {SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT} min",
        ):
            validate_routine_creation(new, "Europe/Paris")

    def test_the_operator_can_allow_every_five_minutes_all_day(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_routine_caps(monkeypatch, min_step_minutes=5, max_times_per_day=288)
        new = ScheduledActionCreate(title="t", action_prompt="p", recurrence=every(5))

        validate_routine_creation(new, "Europe/Paris")  # must not raise

        assert new.recurrence is not None
        assert new.recurrence.per_day() == 288

    def test_an_update_reads_the_caps_at_validation_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_routine_caps(monkeypatch, min_step_minutes=5, max_times_per_day=288)
        assert ScheduledActionUpdate(recurrence=every(5)).recurrence is not None

        pin_routine_caps(monkeypatch)
        with pytest.raises(ValidationError):
            ScheduledActionUpdate(recurrence=every(5))

    def test_a_stored_routine_stays_readable_when_the_caps_are_lowered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cap bounds what is WRITTEN, never what is read back.

        The Studio re-reads every stored routine through the creation schema to
        snapshot it; were the caps checked there, lowering them would make a
        denser routine saved under the old ones impossible to run, rename or
        switch off from the chat. Its schedule only meets the new caps when it
        is changed.
        """
        pin_routine_caps(monkeypatch)
        stored = every(5)  # saved while the operator allowed every five minutes

        snapshot = ScheduledActionCreate(title="t", action_prompt="p", recurrence=stored)
        assert ScheduledActionUpdate(title="renamed").recurrence is None
        with pytest.raises(ValidationError):
            ScheduledActionUpdate(recurrence=stored)

        assert snapshot.recurrence == stored

    def test_the_list_publishes_the_caps_the_validators_apply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The form reads these instead of a copy typed into the browser (ADR-184)."""
        pin_routine_caps(monkeypatch, min_step_minutes=5, max_times_per_day=288)

        published = ScheduledActionListResponse(scheduled_actions=[], total=0).model_dump(
            mode="json"
        )

        assert published["recurrence_limits"] == {
            "min_step_minutes": 5,
            "max_times_per_day": 288,
            "max_series_count": RECURRENCE_ROUTINE_MAX_SERIES_COUNT,
        }

    def test_the_chat_tool_manifest_publishes_the_reader_s_caps(self) -> None:
        """Built at import from the same reader: the planner reads the bound the tool applies."""
        from src.domains.agents.automation.catalogue_manifests import (
            create_scheduled_action_catalogue_manifest,
        )

        params = {p.name: p for p in create_scheduled_action_catalogue_manifest.parameters}
        minimum = next(c.value for c in params["every_minutes"].constraints if c.kind == "minimum")
        most = next(c.value for c in params["times"].constraints if c.kind == "max_length")
        limits = routine_recurrence_limits()

        assert (minimum, most) == (limits.min_step_minutes, limits.max_times_per_day)


#: Who may name a cap: the defaults, the settings, and the one reader.
_OWNERS = frozenset(
    {
        "core/constants.py",
        "core/config/scheduler.py",
        "domains/scheduled_actions/recurrence_limits.py",
    }
)
_CAP_NAMES = frozenset(
    {
        "scheduled_actions_min_step_minutes",
        "scheduled_actions_max_times_per_day",
        "SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT",
        "SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT",
    }
)


def cap_reads(source: str) -> list[str]:
    """Every read of a routine cap in ``source``, as ``"<line> <name>"``.

    Args:
        source: A Python module.

    Returns:
        The attribute reads, names and imports that name a cap.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute):
            names = [node.attr]
        elif isinstance(node, ast.Name):
            names = [node.id]
        elif isinstance(node, ast.ImportFrom):
            names = [alias.name for alias in node.names]
        else:
            continue
        found.extend(f"{node.lineno} {name}" for name in names if name in _CAP_NAMES)
    return found


class TestOneReaderForTheCaps:
    """Every read of the two caps in ``src`` goes through ``routine_recurrence_limits``.

    A validator reading a default constant, or the setting directly, is how the
    form and the API came to say two different minimums — the guard refuses it
    before it ships.
    """

    def test_the_guard_sees_each_shape_of_a_read(self) -> None:
        assert cap_reads("x = settings.scheduled_actions_min_step_minutes\n") == [
            "1 scheduled_actions_min_step_minutes"
        ]
        assert cap_reads(
            "from src.core.constants import SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT\n"
        ) == ["1 SCHEDULED_ACTIONS_MAX_TIMES_PER_DAY_DEFAULT"]
        assert cap_reads("limit = SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT\n") == [
            "1 SCHEDULED_ACTIONS_MIN_STEP_MINUTES_DEFAULT"
        ]
        assert cap_reads("y = routine_recurrence_limits().min_step_minutes\n") == []

    def test_no_other_module_reads_a_cap(self) -> None:
        # The scan walks the real tree: a wrong root would pass on nothing.
        assert (_SRC / "domains" / "scheduled_actions" / "recurrence_limits.py").is_file()
        offenders: list[str] = []
        for path in _SRC.rglob("*.py"):
            relative = path.relative_to(_SRC).as_posix()
            text = path.read_text(encoding="utf-8")
            if relative in _OWNERS or not any(name in text for name in _CAP_NAMES):
                continue
            offenders.extend(f"{relative}:{read}" for read in cap_reads(text))

        assert offenders == []
