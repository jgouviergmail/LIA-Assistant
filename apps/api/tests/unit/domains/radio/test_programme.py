"""The running order: projected air times, re-anchored on the player's reports."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.domains.radio.constants import SIGN_OFF_WINDOW_SECONDS
from src.domains.radio.formats import FORMAT_SPECS, RadioFormat
from src.domains.radio.grid import GridDecision, GridInputs, GridReason, next_segment
from src.domains.radio.programme import (
    Slot,
    aired_segments,
    append,
    following,
    hand_over_to,
    mark_aired,
    mark_produced,
    next_air_at,
    preceding,
    remove,
)
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)


def decision(fmt: RadioFormat, station_id: bool = False) -> GridDecision:
    return GridDecision(format=fmt, reason=GridReason.ROTATION, station_id_due=station_id)


def planned(*formats: RadioFormat) -> tuple[Slot, ...]:
    slots: tuple[Slot, ...] = ()
    for fmt in formats:
        slots = append(slots, decision(fmt), next_air_at(slots, now=NOW, first_delay_s=15))
    return slots


def test_the_first_slot_airs_once_it_can_be_produced() -> None:
    [opening] = planned(RadioFormat.OPENING)
    assert opening.seq == 1
    assert opening.air_at == NOW + timedelta(seconds=15)
    assert opening.duration_s == FORMAT_SPECS[RadioFormat.OPENING].target_seconds


def test_each_slot_follows_the_projected_end_of_the_one_before() -> None:
    opening, brief = planned(RadioFormat.OPENING, RadioFormat.BRIEF)
    assert brief.air_at == opening.ends_at
    assert brief.seq == 2


def test_a_real_duration_moves_what_follows() -> None:
    slots = planned(RadioFormat.OPENING, RadioFormat.BRIEF, RadioFormat.HEADLINES)
    moved = mark_produced(slots, 1, 40.0)
    assert moved[1].air_at == moved[0].air_at + timedelta(seconds=40)
    assert moved[2].air_at == moved[1].ends_at


def test_the_players_report_re_anchors_the_rest() -> None:
    slots = planned(RadioFormat.OPENING, RadioFormat.BRIEF)
    late = NOW + timedelta(minutes=2)
    moved = mark_aired(slots, 1, late.astimezone(timezone(timedelta(hours=2))))
    assert moved[0].reported and moved[0].air_at == late
    assert moved[1].air_at == late + timedelta(seconds=moved[0].duration_s)


def test_a_reported_slot_is_never_moved_by_a_later_estimate() -> None:
    slots = mark_aired(planned(RadioFormat.OPENING, RadioFormat.BRIEF), 2, NOW)
    moved = mark_produced(slots, 1, 999.0)
    assert moved[1].air_at == NOW


def test_after_a_gap_the_next_slot_airs_now_not_in_the_past() -> None:
    slots = planned(RadioFormat.OPENING)
    later = NOW + timedelta(hours=1)
    assert next_air_at(slots, now=later, first_delay_s=15) == later


def test_the_writer_knows_what_comes_before_and_after() -> None:
    slots = planned(RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.HEADLINES)
    assert following(slots, 2) is RadioFormat.HEADLINES
    assert preceding(slots, 2) is RadioFormat.OPENING
    assert following(slots, 3) is None and preceding(slots, 1) is None
    assert following(slots, 99) is None


def test_a_writer_does_not_announce_a_successor_that_may_fail() -> None:
    slots = planned(RadioFormat.OPENING, RadioFormat.JOURNAL, RadioFormat.HEADLINES)
    assert hand_over_to(slots, 1, ready=set()) is None
    assert following(remove(slots, 2), 1) is RadioFormat.HEADLINES
    assert hand_over_to(slots, 1, ready={2}) is RadioFormat.JOURNAL
    assert hand_over_to(slots, 2, ready={3}) is RadioFormat.HEADLINES
    assert hand_over_to(slots, 99, ready={2, 3}) is None


def test_the_grid_reads_planned_slots_as_aired() -> None:
    slots = append(
        (),
        decision(RadioFormat.OPENING, station_id=True),
        NOW,
    )
    [aired] = aired_segments(slots)
    assert (aired.format, aired.air_at, aired.station_id) == (RadioFormat.OPENING, NOW, True)


def test_an_unknown_slot_changes_nothing() -> None:
    slots = planned(RadioFormat.OPENING)
    assert mark_aired(slots, 7, NOW) == slots
    assert mark_produced(slots, 7, 10.0) == slots


def test_a_naive_air_time_is_refused() -> None:
    with pytest.raises(ValueError):
        Slot(
            seq=1,
            format=RadioFormat.OPENING,
            station_id=False,
            air_at=datetime(2026, 9, 26, 9, 0),
            duration_s=25.0,
        )


@pytest.mark.parametrize("seed", range(40))
def test_a_half_hour_before_nine_airs_the_nine_oclock_bulletin_then_signs_off(seed: int) -> None:
    started = NOW  # 08:50 UTC, a 30-minute timer
    stop_at = started + timedelta(minutes=30)
    rng = random.Random(seed)
    slots: tuple[Slot, ...] = ()
    now = started
    while not slots or slots[-1].format is not RadioFormat.SIGN_OFF:
        air_at = next_air_at(slots, now=now, first_delay_s=15)
        inputs = GridInputs(
            session_started_at=started,
            aired=aired_segments(slots),
            air_at=air_at,
            timezone=UTC,
            frequencies={},
            available=frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW},
            public_mode=False,
            voices_by_format=voices_by_format(2),
            stop_at=stop_at,
        )
        choice = next_segment(inputs, rng)
        if choice is None:
            # Nothing fits yet: the station's music plays, the grid is asked again.
            now = air_at + timedelta(seconds=10)
            assert now < stop_at, "the grid never called its farewell"
            continue
        slots = append(slots, choice, air_at)
    formats = [slot.format for slot in slots]
    assert formats[0] is RadioFormat.OPENING and formats[-1] is RadioFormat.SIGN_OFF
    nine = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    assert any(
        s.format is RadioFormat.BULLETIN and nine <= s.air_at < nine + timedelta(minutes=20)
        for s in slots
    )
    assert slots[-1].air_at >= stop_at - timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
    assert slots[-1].ends_at <= stop_at


#: The station's music between two programmes (ADR-324 decision 36).
GAP_S = 5.0


def test_the_music_between_two_programmes_moves_the_next_one_never_the_first() -> None:
    slots: tuple[Slot, ...] = ()
    for fmt in (RadioFormat.OPENING, RadioFormat.BRIEF):
        air_at = next_air_at(slots, now=NOW, first_delay_s=15, gap_s=GAP_S)
        slots = append(slots, decision(fmt), air_at)
    opening, brief = slots
    assert opening.air_at == NOW + timedelta(seconds=15)
    assert brief.air_at == opening.ends_at + timedelta(seconds=GAP_S)


def test_every_projection_keeps_the_music_between_programmes() -> None:
    slots = planned(RadioFormat.OPENING, RadioFormat.BRIEF, RadioFormat.HEADLINES)
    produced = mark_produced(slots, 1, 40.0, gap_s=GAP_S)
    assert produced[1].air_at == produced[0].ends_at + timedelta(seconds=GAP_S)
    assert produced[2].air_at == produced[1].ends_at + timedelta(seconds=GAP_S)
    aired = mark_aired(slots, 1, NOW, gap_s=GAP_S)
    assert aired[1].air_at == aired[0].ends_at + timedelta(seconds=GAP_S)
    removed = remove(slots, 2, gap_s=GAP_S)
    assert removed[1].air_at == slots[1].air_at  # the next one takes the removed one's place
