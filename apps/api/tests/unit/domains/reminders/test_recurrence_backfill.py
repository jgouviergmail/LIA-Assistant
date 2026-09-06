"""What the migration writes into `reminders.recurrence`, frozen.

The backfill is one SQL statement (`_TO_RECURRENCE` in
``2026_09_06_0100-f0a1b2c3d4e5_reminder_recurrence.py``): it reads the UTC
instant a reminder already carries and the row's own timezone, and writes the
LOCAL wall clock as a `once` recurrence.

The cases below were produced by that statement on real PostgreSQL 16 on
2026-09-06 and pasted here verbatim. Freezing them rather than re-running the
SQL is deliberate, for the reason ADR-245's golden file gives: this must keep
answering after the migration has been applied everywhere and nobody runs it
again.

Three properties, and the third is the one the whole lot rests on:

1. the JSON the SQL builds is **byte-identical** to what the model dumps, so a
   migrated row and an API-written row are the same row;
2. the spec names the reader's own wall clock, whatever the offset — including
   the two Paris seasons, Kathmandu's `+05:45` and Chatham's `+13:45`, which
   lands the local date on the NEXT day;
3. re-arming a consumed single occurrence answers ``None`` — which the
   scheduler reads as "delete". That is the historical one-shot behaviour,
   expressed as the general rule instead of a special case.
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.recurrence import RecurrenceSpec, rearm_after

pytestmark = pytest.mark.unit

#: (label, IANA zone, local wall clock the SQL derived, the JSON it wrote).
#: Captured from `psql` on the dev database, 2026-09-06.
BACKFILLED: list[tuple[str, str, str, str]] = [
    (
        "Paris winter",
        "Europe/Paris",
        "2026-01-15 10:00:00",
        '{"end": {"kind": "never", "on_date": null, "after_count": null}, "freq": "once",'
        ' "times": {"at": [{"hour": 10, "minute": 0}], "end": null, "mode": "at",'
        ' "start": null, "step_minutes": null}, "bymonth": [], "interval": 1,'
        ' "byweekday": [], "bymonthday": [], "anchor_date": "2026-01-15",'
        ' "nth_weekday": null}',
    ),
    (
        "Paris summer",
        "Europe/Paris",
        "2026-07-15 10:00:00",
        '{"end": {"kind": "never", "on_date": null, "after_count": null}, "freq": "once",'
        ' "times": {"at": [{"hour": 10, "minute": 0}], "end": null, "mode": "at",'
        ' "start": null, "step_minutes": null}, "bymonth": [], "interval": 1,'
        ' "byweekday": [], "bymonthday": [], "anchor_date": "2026-07-15",'
        ' "nth_weekday": null}',
    ),
    (
        "Kathmandu +05:45",
        "Asia/Kathmandu",
        "2026-03-10 10:00:00",
        '{"end": {"kind": "never", "on_date": null, "after_count": null}, "freq": "once",'
        ' "times": {"at": [{"hour": 10, "minute": 0}], "end": null, "mode": "at",'
        ' "start": null, "step_minutes": null}, "bymonth": [], "interval": 1,'
        ' "byweekday": [], "bymonthday": [], "anchor_date": "2026-03-10",'
        ' "nth_weekday": null}',
    ),
    (
        "Chatham +13:45, next local day",
        "Pacific/Chatham",
        "2026-03-11 10:00:00",
        '{"end": {"kind": "never", "on_date": null, "after_count": null}, "freq": "once",'
        ' "times": {"at": [{"hour": 10, "minute": 0}], "end": null, "mode": "at",'
        ' "start": null, "step_minutes": null}, "bymonth": [], "interval": 1,'
        ' "byweekday": [], "bymonthday": [], "anchor_date": "2026-03-11",'
        ' "nth_weekday": null}',
    ),
    (
        "seconds are dropped by the spec, kept by the instant",
        "UTC",
        "2026-03-10 10:00:00",
        '{"end": {"kind": "never", "on_date": null, "after_count": null}, "freq": "once",'
        ' "times": {"at": [{"hour": 10, "minute": 0}], "end": null, "mode": "at",'
        ' "start": null, "step_minutes": null}, "bymonth": [], "interval": 1,'
        ' "byweekday": [], "bymonthday": [], "anchor_date": "2026-03-10",'
        ' "nth_weekday": null}',
    ),
]


@pytest.mark.parametrize(("label", "zone", "wall", "raw"), BACKFILLED, ids=lambda v: str(v)[:24])
class TestTheBackfillProducesAReadableSpec:
    def test_the_sql_shape_is_the_model_shape(
        self, label: str, zone: str, wall: str, raw: str
    ) -> None:
        """A migrated row and an API-written row must be the same row.

        The SQL first omitted `step_minutes`, `start` and `end` — read back
        identically, since the model fills them, but stored differently. The
        column is the same column; it should hold the same document.
        """
        payload = json.loads(raw)
        assert RecurrenceSpec.model_validate(payload).model_dump(mode="json") == payload

    def test_the_spec_names_the_readers_own_wall_clock(
        self, label: str, zone: str, wall: str, raw: str
    ) -> None:
        spec = RecurrenceSpec.model_validate(json.loads(raw))
        expected = datetime.fromisoformat(wall)
        assert spec.anchor_date == expected.date()
        assert (spec.times.at[0].hour, spec.times.at[0].minute) == (
            expected.hour,
            expected.minute,
        )

    def test_a_consumed_single_occurrence_arms_nothing(
        self, label: str, zone: str, wall: str, raw: str
    ) -> None:
        """`None` is what the scheduler reads as "delete".

        This is the whole reason the reminder domain needs no new state: the
        post-it behaviour falls out of the general rule.
        """
        spec = RecurrenceSpec.model_validate(json.loads(raw))
        instant = datetime.fromisoformat(wall).replace(tzinfo=ZoneInfo(zone))
        assert rearm_after(spec, zone, due_at=instant, now=instant) is None


def test_a_repeating_reminder_arms_its_next_occurrence() -> None:
    """The counterpart: what the backfill can never produce, but a user can.

    Same function, same row, opposite answer — no branch reads "is this
    recurring".
    """
    spec = RecurrenceSpec.model_validate(
        {
            "freq": "daily",
            "interval": 1,
            "anchor_date": "2026-03-10",
            "times": {"mode": "at", "at": [{"hour": 10, "minute": 0}]},
        }
    )
    instant = datetime(2026, 3, 10, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))
    armed = rearm_after(spec, "Europe/Paris", due_at=instant, now=instant)
    assert armed is not None
    assert (
        armed.astimezone(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d %H:%M") == "2026-03-11 10:00"
    )


class TestTheServiceAndTheMigrationAgree:
    """Two ways in, one description of "this happens once".

    The migration derived a spec for rows that already existed; the service
    derives one for rows created without a recurrence. If those two ever
    disagreed, a reminder's schedule would depend on WHEN it was created,
    which is the drift this lot exists to remove.
    """

    @pytest.mark.parametrize(
        ("label", "zone", "wall", "raw"), BACKFILLED, ids=lambda v: str(v)[:24]
    )
    def test_the_service_derives_what_the_migration_wrote(
        self, label: str, zone: str, wall: str, raw: str
    ) -> None:
        from src.domains.reminders.service import once_at

        instant = datetime.fromisoformat(wall).replace(tzinfo=ZoneInfo(zone))
        assert once_at(instant, zone).model_dump(mode="json") == json.loads(raw)

    def test_the_derivation_reads_the_users_zone_not_the_servers(self) -> None:
        """The same instant, described by two readers, is two wall clocks."""
        from src.domains.reminders.service import once_at

        instant = datetime(2026, 3, 10, 22, 30, tzinfo=ZoneInfo("UTC"))
        paris = once_at(instant, "Europe/Paris")
        tokyo = once_at(instant, "Asia/Tokyo")

        assert (paris.anchor_date.isoformat(), paris.times.at[0].hour) == ("2026-03-10", 23)
        # Tokyo is already the next day.
        assert (tokyo.anchor_date.isoformat(), tokyo.times.at[0].hour) == ("2026-03-11", 7)
