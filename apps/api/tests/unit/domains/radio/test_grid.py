"""The grid decides the antenna's rhythm without a model — rule by rule, then at scale."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest

from src.domains.radio.constants import (
    BRIEF_MAX_PER_WINDOW,
    BRIEF_WINDOW_SECONDS,
    FAILED_FORMAT_REST_SECONDS,
    SIGN_OFF_WINDOW_SECONDS,
    STATION_ID_INTERVAL_SECONDS,
)
from src.domains.radio.formats import (
    FORMAT_SPECS,
    Frequency,
    JournalEdition,
    Material,
    RadioFormat,
    journal_edition,
    selectable_formats,
)
from src.domains.radio.grid import (
    AiredSegment,
    GridDecision,
    GridInputs,
    GridReason,
    is_eligible,
    next_segment,
)
from tests.unit.domains.radio.fakes import voices_by_format

pytestmark = pytest.mark.unit

#: Every format has something to say — never « nothing new », which the desk offers
#: only when the listener heard every story left.
ALL = frozenset(RadioFormat) - {RadioFormat.NOTHING_NEW}
START = datetime(2026, 9, 26, 8, 50, tzinfo=UTC)
#: How far the simulated clock moves while the station's music fills a gap.
MUSIC_STEP_SECONDS = 30


def inputs(
    *,
    aired: tuple[AiredSegment, ...] = (),
    air_at: datetime | None = None,
    started: datetime = START,
    tz: tzinfo = UTC,
    frequencies: dict[RadioFormat, Frequency] | None = None,
    available: frozenset[RadioFormat] = ALL,
    public_mode: bool = False,
    voices: int = 4,
    stop_at: datetime | None = None,
) -> GridInputs:
    return GridInputs(
        session_started_at=started,
        aired=aired,
        air_at=air_at or started,
        timezone=tz,
        frequencies=frequencies or {},
        available=available,
        public_mode=public_mode,
        voices_by_format=voices_by_format(voices),
        stop_at=stop_at,
    )


def seg(fmt: RadioFormat, minutes: float, *, station_id: bool = False) -> AiredSegment:
    return AiredSegment(fmt, START + timedelta(minutes=minutes), station_id)


def decide(i: GridInputs, seed: int = 0) -> GridDecision | None:
    return next_segment(i, random.Random(seed))


class TestForcedRules:
    def test_an_empty_session_opens_and_names_the_station(self) -> None:
        decision = decide(inputs())
        assert decision == GridDecision(RadioFormat.OPENING, GridReason.OPENING, True)

    def test_after_the_opening_comes_the_listeners_journal(self) -> None:
        decision = decide(inputs(aired=(seg(RadioFormat.OPENING, 0, station_id=True),)))
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.JOURNAL, GridReason.DAY_START)

    def test_without_a_day_to_tell_the_opening_hands_over_to_the_headlines(self) -> None:
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),), available=ALL - {RadioFormat.JOURNAL})
        decision = decide(i)
        assert decision is not None and decision.format is RadioFormat.HEADLINES

    def test_public_mode_never_tells_the_persons_day(self) -> None:
        decision = decide(inputs(aired=(seg(RadioFormat.OPENING, 0),), public_mode=True))
        assert decision is not None and decision.format is RadioFormat.HEADLINES

    def test_the_sign_off_ends_the_session(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.SIGN_OFF, 1))
        assert decide(inputs(aired=aired)) is None

    def test_the_timer_calls_the_sign_off(self) -> None:
        air_at = START + timedelta(minutes=29)
        stop_at = air_at + timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),), air_at=air_at, stop_at=stop_at)
        decision = decide(i)
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.SIGN_OFF, GridReason.SIGN_OFF)

    def test_the_top_of_the_hour_is_a_bulletin_announced_for_that_hour(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.HEADLINES, 1))
        air_at = datetime(2026, 9, 26, 9, 3, tzinfo=UTC)
        decision = decide(inputs(aired=aired, air_at=air_at))
        assert decision is not None
        assert decision.format is RadioFormat.BULLETIN
        assert decision.reason is GridReason.TOP_OF_HOUR
        assert decision.clock_mark == datetime(2026, 9, 26, 9, 0, tzinfo=UTC)

    def test_a_bulletin_already_aired_this_hour_is_not_repeated_by_the_clock(self) -> None:
        aired = (
            seg(RadioFormat.OPENING, 0),
            seg(RadioFormat.BULLETIN, 11),  # 09:01
            seg(RadioFormat.BRIEF, 15),
        )
        air_at = datetime(2026, 9, 26, 9, 8, tzinfo=UTC)
        decision = decide(inputs(aired=aired, air_at=air_at))
        assert decision is not None and decision.reason is not GridReason.TOP_OF_HOUR

    def test_a_mark_passed_too_long_ago_is_not_announced(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.HEADLINES, 1))
        air_at = datetime(2026, 9, 26, 9, 25, tzinfo=UTC)  # 25 min after the hour
        decision = decide(inputs(aired=aired, air_at=air_at))
        assert decision is not None and decision.reason is not GridReason.TOP_OF_HOUR

    def test_headlines_at_twenty_past(self) -> None:
        started = datetime(2026, 9, 26, 10, 1, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
        )
        air_at = datetime(2026, 9, 26, 10, 22, tzinfo=UTC)
        decision = decide(inputs(aired=aired, air_at=air_at, started=started))
        assert decision is not None
        assert decision.reason is GridReason.HEADLINES_MARK
        assert decision.clock_mark == datetime(2026, 9, 26, 10, 20, tzinfo=UTC)

    def test_a_journal_with_nothing_to_say_at_the_start_comes_once_it_has(self) -> None:
        """The headlines opened the session (the day was empty); the moment the journal has
        something to say, it is due — once for its edition."""
        started = datetime(2026, 9, 26, 19, 0, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.HEADLINES, started + timedelta(minutes=1)),
        )
        air_at = started + timedelta(minutes=6)
        decision = decide(inputs(aired=aired, air_at=air_at, started=started))
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )
        again = aired + (
            AiredSegment(RadioFormat.JOURNAL, air_at),
            AiredSegment(RadioFormat.BRIEF, air_at),
        )
        later = decide(inputs(aired=again, air_at=air_at + timedelta(minutes=5), started=started))
        assert later is not None and later.format is not RadioFormat.JOURNAL

    def test_the_journal_is_never_drawn_a_second_time_in_its_edition(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        only = frozenset({RadioFormat.JOURNAL})
        assert (
            decide(inputs(aired=aired, air_at=START + timedelta(minutes=8), available=only)) is None
        )


class TestDaylightSavingTime:
    def test_the_repeated_hour_still_opens_a_bulletin(self) -> None:
        """2026-11-01 in New York: 01:00-02:00 happens twice.

        A session that starts at 01:10 EDT and reaches 01:05 EST crossed the top
        of an hour (06:00 UTC). Compared on wall clocks — same tzinfo — 01:00
        looks earlier than the 01:10 start and the bulletin is never offered.
        """
        tz = ZoneInfo("America/New_York")
        started = datetime(2026, 11, 1, 5, 10, tzinfo=UTC)  # 01:10 EDT
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.HEADLINES, started + timedelta(minutes=1)),
        )
        air_at = datetime(2026, 11, 1, 6, 5, tzinfo=UTC)  # 01:05 EST
        decision = decide(inputs(aired=aired, air_at=air_at, started=started, tz=tz))
        assert decision is not None
        assert decision.reason is GridReason.TOP_OF_HOUR
        assert decision.clock_mark is not None
        assert decision.clock_mark.astimezone(UTC) == datetime(2026, 11, 1, 6, 0, tzinfo=UTC)

    def test_marks_are_read_on_the_persons_clock(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")  # +05:30: its top of the hour is :30 UTC
        started = datetime(2026, 9, 26, 3, 20, tzinfo=UTC)  # 08:50 IST
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.HEADLINES, started + timedelta(minutes=1)),
        )
        air_at = datetime(2026, 9, 26, 3, 32, tzinfo=UTC)  # 09:02 IST
        decision = decide(inputs(aired=aired, air_at=air_at, started=started, tz=tz))
        assert decision is not None and decision.reason is GridReason.TOP_OF_HOUR


class TestInstants:
    def test_a_naive_instant_is_refused(self) -> None:
        with pytest.raises(ValueError, match="aware"):
            AiredSegment(RadioFormat.BRIEF, datetime(2026, 9, 26, 9, 0))
        with pytest.raises(ValueError, match="aware"):
            inputs(stop_at=datetime(2026, 9, 26, 9, 0))

    def test_local_instants_are_measured_as_instants(self) -> None:
        """A gap straddling the fall-back hour, given in LOCAL time, is its real length."""
        tz = ZoneInfo("America/New_York")
        first = datetime(2026, 11, 1, 5, 50, tzinfo=UTC).astimezone(tz)  # 01:50 EDT
        later = datetime(2026, 11, 1, 6, 10, tzinfo=UTC).astimezone(tz)  # 01:10 EST
        aired = (
            AiredSegment(RadioFormat.OPENING, first),
            AiredSegment(RadioFormat.ANALYSIS, first),
            AiredSegment(RadioFormat.BRIEF, first),
        )
        i = inputs(aired=aired, air_at=later, started=first, tz=tz)
        # 20 real minutes have passed: the analysis gap (20 min) is honoured,
        # whereas the wall clocks (01:50 then 01:10) would say minus forty.
        assert is_eligible(i, RadioFormat.ANALYSIS) is True


class TestEligibility:
    def test_off_is_never_drawn(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        freqs = dict.fromkeys(RadioFormat, Frequency.OFF)
        assert (
            decide(inputs(aired=aired, air_at=START + timedelta(minutes=5), frequencies=freqs))
            is None
        )

    def test_a_format_without_material_is_never_drawn(self) -> None:
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),), available=frozenset())
        assert is_eligible(i, RadioFormat.BRIEF) is False

    def test_a_dialogue_needs_two_voices(self) -> None:
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),), voices=1)
        assert is_eligible(i, RadioFormat.ANALYSIS) is False
        assert is_eligible(i, RadioFormat.COLUMN) is True  # a monologue needs one

    def test_the_same_format_never_airs_twice_in_a_row(self) -> None:
        i = inputs(
            aired=(seg(RadioFormat.OPENING, 0), seg(RadioFormat.BRIEF, 1)),
            air_at=START + timedelta(minutes=10),
        )
        assert is_eligible(i, RadioFormat.BRIEF) is False

    def test_briefs_are_capped_per_window(self) -> None:
        aired = [seg(RadioFormat.OPENING, 0)]
        for n in range(BRIEF_MAX_PER_WINDOW):
            aired += [
                seg(RadioFormat.BRIEF, 2 + n * 4),
                seg(RadioFormat.NUMBER if n == 0 else RadioFormat.HEADLINES, 3 + n * 4),
            ]
        i = inputs(aired=tuple(aired), air_at=START + timedelta(minutes=20))
        assert is_eligible(i, RadioFormat.BRIEF) is False
        after = inputs(
            aired=tuple(aired), air_at=START + timedelta(seconds=BRIEF_WINDOW_SECONDS + 600)
        )
        assert is_eligible(after, RadioFormat.BRIEF) is True

    def test_a_format_that_would_outlast_the_timer_is_not_planned(self) -> None:
        air_at = START + timedelta(minutes=10)
        spec = FORMAT_SPECS[RadioFormat.BULLETIN]
        stop_at = air_at + timedelta(seconds=spec.target_seconds + SIGN_OFF_WINDOW_SECONDS - 1)
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),), air_at=air_at, stop_at=stop_at)
        assert is_eligible(i, RadioFormat.BULLETIN) is False
        assert is_eligible(i, RadioFormat.BRIEF) is True

    def test_the_station_formats_are_never_drawn(self) -> None:
        i = inputs(aired=(seg(RadioFormat.OPENING, 0),))
        assert is_eligible(i, RadioFormat.OPENING) is False
        assert is_eligible(i, RadioFormat.SIGN_OFF) is False

    def test_station_id_is_due_again_after_the_interval(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0, station_id=True), seg(RadioFormat.JOURNAL, 1))
        soon = decide(inputs(aired=aired, air_at=START + timedelta(minutes=5)))
        later = decide(
            inputs(aired=aired, air_at=START + timedelta(seconds=STATION_ID_INTERVAL_SECONDS))
        )
        assert soon is not None and soon.station_id_due is False
        assert later is not None and later.station_id_due is True


def _simulate(rng: random.Random) -> list[tuple[GridInputs, GridDecision]]:
    """One random session, driven by the grid itself until it stops."""
    tz: tzinfo = rng.choice([UTC, ZoneInfo("America/New_York"), ZoneInfo("Asia/Shanghai")])
    started = datetime(2026, 9, 26, 0, 0, tzinfo=UTC) + timedelta(minutes=rng.randrange(0, 24 * 60))
    # What a listener may set: the settings refuse a frequency for the station's own formats.
    frequencies = {
        fmt: rng.choice(list(Frequency)) for fmt in selectable_formats() if rng.random() < 0.6
    }
    available = frozenset(fmt for fmt in RadioFormat if rng.random() < 0.8)
    public_mode = rng.random() < 0.2
    voices = rng.choice([1, 2, 4])
    stop_at = started + timedelta(minutes=rng.choice([15, 30, 60])) if rng.random() < 0.8 else None
    aired: list[AiredSegment] = []
    trace: list[tuple[GridInputs, GridDecision]] = []
    air_at = started
    for _ in range(600):
        i = GridInputs(
            started,
            tuple(aired),
            air_at,
            tz,
            frequencies,
            available,
            public_mode,
            voices_by_format(voices),
            stop_at,
        )
        decision = next_segment(i, rng)
        if decision is None:
            if stop_at is None:
                break
            # Nothing fits yet: the station's music plays, and the grid is asked again.
            air_at += timedelta(seconds=MUSIC_STEP_SECONDS)
            continue
        trace.append((i, decision))
        aired.append(AiredSegment(decision.format, air_at, decision.station_id_due))
        if decision.format is RadioFormat.SIGN_OFF:
            break
        air_at += timedelta(seconds=FORMAT_SPECS[decision.format].target_seconds)
    return trace


def _assert_hard_rules(i: GridInputs, decision: GridDecision) -> None:
    """The hard rules hold for every decision, the FILL draw included."""
    spec = FORMAT_SPECS[decision.format]
    assert decision.format in i.available
    assert i.frequencies.get(decision.format, spec.default_frequency) is not Frequency.OFF
    assert not (i.public_mode and spec.material is Material.PERSONAL)
    assert spec.min_distinct_voices <= i.voices_by_format.get(decision.format, 0)
    if i.stop_at is not None:
        assert i.air_at + timedelta(seconds=spec.target_seconds) <= i.stop_at


def _assert_variety_rules(i: GridInputs, decision: GridDecision, previous: RadioFormat) -> None:
    """The variety rules hold for every decision but the FILL draw."""
    if decision.reason is GridReason.FILL:
        return
    assert decision.format is not previous, "never twice in a row"
    if decision.format is RadioFormat.BRIEF:
        since = i.air_at - timedelta(seconds=BRIEF_WINDOW_SECONDS)
        before = [s for s in i.aired if s.format is RadioFormat.BRIEF and s.air_at > since]
        assert len(before) < BRIEF_MAX_PER_WINDOW


def _assert_session_bounds(formats: list[RadioFormat]) -> None:
    """Each format within its per-session cap, and the farewell the last word."""
    for fmt, spec in FORMAT_SPECS.items():
        if spec.max_per_session is not None:
            assert formats.count(fmt) <= spec.max_per_session
    if RadioFormat.SIGN_OFF in formats:
        assert formats[-1] is RadioFormat.SIGN_OFF


def _assert_journal_by_edition(trace: list[tuple[GridInputs, GridDecision]]) -> None:
    """The journal airs once per edition of the listener's day, and only when the grid calls
    it — the draw never reaches it."""
    editions: set[tuple[object, JournalEdition]] = set()
    for i, decision in trace:
        if decision.format is not RadioFormat.JOURNAL:
            continue
        assert decision.reason in {GridReason.DAY_START, GridReason.JOURNAL_EDITION}
        local = i.air_at.astimezone(i.timezone)
        edition = (local.date(), journal_edition(local))
        assert edition not in editions, edition
        editions.add(edition)


def _assert_farewell_on_time(trace: list[tuple[GridInputs, GridDecision]]) -> None:
    """A timed session always ends on its farewell, and never before the window."""
    first, _ = trace[0]
    if first.stop_at is None:
        return
    last_inputs, last = trace[-1]
    assert last.format is RadioFormat.SIGN_OFF
    assert last_inputs.stop_at is not None
    window_opens = last_inputs.stop_at - timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
    assert last_inputs.air_at >= window_opens, "the farewell never comes early"


@pytest.mark.parametrize("seed", range(300))
def test_three_hundred_random_sessions_keep_every_invariant(seed: int) -> None:
    trace = _simulate(random.Random(seed))
    assert trace and trace[0][1].format is RadioFormat.OPENING
    formats = [decision.format for _, decision in trace]
    for (i, decision), previous in zip(trace[1:], formats, strict=False):
        if decision.format is RadioFormat.SIGN_OFF:
            continue
        _assert_hard_rules(i, decision)
        _assert_variety_rules(i, decision, previous)
    _assert_session_bounds(formats)
    _assert_journal_by_edition(trace)
    _assert_farewell_on_time(trace)


class TestFill:
    def test_a_station_of_briefs_keeps_airing_briefs(self) -> None:
        only = frozenset({RadioFormat.BRIEF})
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.BRIEF, 1))
        decision = decide(inputs(aired=aired, air_at=START + timedelta(minutes=2), available=only))
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.BRIEF, GridReason.FILL)

    def test_the_fill_draw_never_crosses_a_hard_rule(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        only = frozenset({RadioFormat.JOURNAL})  # already aired once: its bound holds
        assert (
            decide(inputs(aired=aired, air_at=START + timedelta(minutes=5), available=only)) is None
        )

    def test_nothing_left_to_say_is_none(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0),)
        assert decide(inputs(aired=aired, available=frozenset())) is None

    def test_with_nothing_left_before_the_window_the_music_plays_on(self) -> None:
        # 100 s left: the shortest format and the farewell window no longer
        # fit, yet the stop is further than the window — nothing is planned,
        # the station's music plays and the grid is asked again (measured
        # 2026-09-26: a farewell said nine minutes before a thirty-minute stop).
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        air_at = START + timedelta(minutes=10)
        stop_at = air_at + timedelta(seconds=100)
        assert decide(inputs(aired=aired, air_at=air_at, stop_at=stop_at)) is None

    def test_asked_again_inside_the_window_the_station_says_goodbye(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        stop_at = START + timedelta(minutes=10, seconds=100)
        air_at = stop_at - timedelta(seconds=SIGN_OFF_WINDOW_SECONDS)
        decision = decide(inputs(aired=aired, air_at=air_at, stop_at=stop_at))
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.SIGN_OFF, GridReason.SIGN_OFF)

    def test_a_station_with_nothing_to_say_never_says_goodbye_early(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0),)
        stop_at = START + timedelta(minutes=30)
        early = inputs(aired=aired, air_at=START + timedelta(minutes=2), available=frozenset())
        timed = inputs(
            aired=aired,
            air_at=START + timedelta(minutes=2),
            available=frozenset(),
            stop_at=stop_at,
        )
        assert decide(early) is None
        assert decide(timed) is None


class TestEditions:
    """ADR-324 decision 41: the journal opens the session in the edition of the moment and
    comes back once when the session crosses into another — the grid calls it, the draw
    never does, and an edition's journal airs once."""

    EVENING = datetime(2026, 9, 26, 19, 20, tzinfo=UTC)
    #: The clock formats left out: a mark would come first, and that is another rule.
    NO_CLOCK = ALL - {RadioFormat.BULLETIN, RadioFormat.HEADLINES}

    def test_in_the_evening_the_session_opens_with_the_evening_edition(self) -> None:
        aired = (AiredSegment(RadioFormat.OPENING, self.EVENING),)
        decision = decide(
            inputs(aired=aired, air_at=self.EVENING + timedelta(minutes=1), started=self.EVENING)
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.JOURNAL, GridReason.DAY_START)

    def test_an_editions_journal_airs_once_whatever_the_draw(self) -> None:
        aired = (
            AiredSegment(RadioFormat.OPENING, self.EVENING),
            AiredSegment(RadioFormat.JOURNAL, self.EVENING + timedelta(minutes=1)),
        )
        at = self.EVENING + timedelta(minutes=20)
        assert (
            is_eligible(inputs(aired=aired, air_at=at, started=self.EVENING), RadioFormat.JOURNAL)
            is False
        )
        only = frozenset({RadioFormat.JOURNAL})
        assert decide(inputs(aired=aired, air_at=at, started=self.EVENING, available=only)) is None

    def test_without_a_journal_the_session_opens_with_the_headlines(self) -> None:
        aired = (AiredSegment(RadioFormat.OPENING, self.EVENING),)
        decision = decide(
            inputs(
                aired=aired,
                air_at=self.EVENING + timedelta(minutes=1),
                started=self.EVENING,
                frequencies={RadioFormat.JOURNAL: Frequency.OFF},
            )
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.HEADLINES, GridReason.DAY_START)

    def test_a_session_that_crosses_into_the_evening_hears_the_evening_edition(self) -> None:
        started = datetime(2026, 9, 26, 17, 55, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=5)),
        )
        decision = decide(
            inputs(
                aired=aired,
                air_at=started + timedelta(minutes=12),
                started=started,
                available=self.NO_CLOCK,
            )
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )

    def test_two_editions_never_come_back_to_back(self) -> None:
        """A session started minutes before the edition changes heard its journal: the next
        edition's waits the journal's own gap — the rotation airs something else."""
        started = datetime(2026, 9, 26, 17, 55, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=5)),
        )
        gap = FORMAT_SPECS[RadioFormat.JOURNAL].min_gap_seconds
        soon = started + timedelta(minutes=1, seconds=gap - 60)  # 18:05, inside the gap
        decision = decide(
            inputs(aired=aired, air_at=soon, started=started, available=self.NO_CLOCK)
        )
        assert decision is not None
        assert decision.format is not RadioFormat.JOURNAL
        assert decision.reason is GridReason.ROTATION

    def test_the_fill_draw_never_reaches_the_journal(self) -> None:
        """A listener who hears the journal alone waits the gap: the fill draw relaxes the
        variety rules for every format but the journal, whose only doors are rules 3 and 5 —
        or the gap would be relaxed by the very draw it exists to hold off."""
        started = datetime(2026, 9, 26, 17, 55, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=5)),
        )
        only = frozenset({RadioFormat.JOURNAL})
        inside_the_gap = started + timedelta(minutes=9)
        assert (
            decide(inputs(aired=aired, air_at=inside_the_gap, started=started, available=only))
            is None
        )
        past_the_gap = started + timedelta(minutes=12)
        decision = decide(inputs(aired=aired, air_at=past_the_gap, started=started, available=only))
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )

    def test_the_clock_comes_before_the_new_edition(self) -> None:
        started = datetime(2026, 9, 26, 11, 50, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
        )
        noon = datetime(2026, 9, 26, 12, 1, tzinfo=UTC)
        first = decide(inputs(aired=aired, air_at=noon, started=started))
        assert first is not None
        assert (first.format, first.reason) == (RadioFormat.BULLETIN, GridReason.TOP_OF_HOUR)
        after_the_news = aired + (AiredSegment(RadioFormat.BULLETIN, noon),)
        then = decide(
            inputs(aired=after_the_news, air_at=noon + timedelta(minutes=5), started=started)
        )
        assert then is not None
        assert (then.format, then.reason) == (RadioFormat.JOURNAL, GridReason.JOURNAL_EDITION)

    def test_past_midnight_the_journal_is_the_next_days(self) -> None:
        started = datetime(2026, 9, 26, 23, 40, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=10)),
        )
        decision = decide(
            inputs(
                aired=aired,
                air_at=started + timedelta(minutes=35),
                started=started,
                available=self.NO_CLOCK,
            )
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )

    def test_a_session_that_runs_a_whole_day_hears_the_next_days_morning(self) -> None:
        """The bound is per edition of the listener's LOCAL DAY: the same edition a day later
        is another journal, not « the morning's again »."""
        started = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=5)),
        )
        a_day_later = started + timedelta(hours=24, minutes=30)
        decision = decide(
            inputs(aired=aired, air_at=a_day_later, started=started, available=self.NO_CLOCK)
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )

    def test_the_edition_is_read_on_the_listeners_clock(self) -> None:
        tz = ZoneInfo("Asia/Kolkata")  # +05:30: 12:35 UTC is 18:05 there, the evening
        started = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)  # 17:30 IST, the noon edition
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
            AiredSegment(RadioFormat.BRIEF, started + timedelta(minutes=10)),
        )
        decision = decide(
            inputs(
                aired=aired,
                air_at=started + timedelta(minutes=35),
                started=started,
                tz=tz,
                available=self.NO_CLOCK,
            )
        )
        assert decision is not None
        assert (decision.format, decision.reason) == (
            RadioFormat.JOURNAL,
            GridReason.JOURNAL_EDITION,
        )
        under_utc = decide(
            inputs(
                aired=aired,
                air_at=started + timedelta(minutes=35),
                started=started,
                available=self.NO_CLOCK,
            )
        )
        assert under_utc is not None and under_utc.format is not RadioFormat.JOURNAL


class TestFailedFormatsRest:
    """A production that failed is paid for: the same format does not try again at once."""

    def failed_at(self, fmt: RadioFormat, minutes: float) -> tuple[AiredSegment, ...]:
        return (AiredSegment(fmt, START + timedelta(minutes=minutes)),)

    def test_a_format_that_just_failed_is_not_drawn_again(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.BRIEF, 1))
        only = frozenset({RadioFormat.ANALYSIS, RadioFormat.BRIEF})
        at = START + timedelta(minutes=4)
        failed = self.failed_at(RadioFormat.ANALYSIS, 3)
        for seed in range(40):
            decision = decide(
                GridInputs(
                    START, aired, at, UTC, {}, only, False, voices_by_format(4), None, failed=failed
                ),
                seed,
            )
            assert decision is not None and decision.format is not RadioFormat.ANALYSIS

    def test_the_rest_is_not_relaxed_by_the_fill_draw(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.BRIEF, 1))
        failed = self.failed_at(RadioFormat.ANALYSIS, 2)
        i = GridInputs(
            START,
            aired,
            START + timedelta(minutes=3),
            UTC,
            {},
            frozenset({RadioFormat.ANALYSIS}),
            False,
            voices_by_format(4),
            None,
            failed=failed,
        )
        assert decide(i) is None

    def test_the_rest_is_the_formats_own_gap_when_longer(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.BRIEF, 1))
        failed = self.failed_at(RadioFormat.ANALYSIS, 2)
        rest = max(FAILED_FORMAT_REST_SECONDS, FORMAT_SPECS[RadioFormat.ANALYSIS].min_gap_seconds)
        only = frozenset({RadioFormat.ANALYSIS})

        def at(seconds: float) -> GridDecision | None:
            return decide(
                GridInputs(
                    START,
                    aired,
                    START + timedelta(minutes=2, seconds=seconds),
                    UTC,
                    {},
                    only,
                    False,
                    voices_by_format(4),
                    None,
                    failed=failed,
                )
            )

        assert at(rest - 1) is None
        rested = at(rest)
        assert rested is not None and rested.format is RadioFormat.ANALYSIS

    def test_the_rest_runs_from_the_latest_failure(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.HEADLINES, 1))
        failed = (
            AiredSegment(RadioFormat.BRIEF, START),
            AiredSegment(RadioFormat.BRIEF, START + timedelta(minutes=10)),
        )
        at = START + timedelta(minutes=11)  # long after the first, just after the second
        i = GridInputs(
            START,
            aired,
            at,
            UTC,
            {},
            frozenset({RadioFormat.BRIEF}),
            False,
            voices_by_format(4),
            None,
            failed=failed,
        )
        assert decide(i) is None

    def test_a_short_gap_still_rests_the_whole_rest(self) -> None:
        # A brief's own gap is two minutes: a failed brief still rests the floor.
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.HEADLINES, 1))
        failed = self.failed_at(RadioFormat.BRIEF, 2)
        just_before = START + timedelta(minutes=2, seconds=FAILED_FORMAT_REST_SECONDS - 1)
        i = GridInputs(
            START,
            aired,
            just_before,
            UTC,
            {},
            frozenset({RadioFormat.BRIEF}),
            False,
            voices_by_format(4),
            None,
            failed=failed,
        )
        assert decide(i) is None

    def test_a_clock_rule_does_not_force_a_format_that_is_resting(self) -> None:
        # The bulletin at the top of the hour failed: it is not forced again at once.
        started = datetime(2026, 9, 26, 8, 30, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started + timedelta(minutes=1)),
        )
        failed = (AiredSegment(RadioFormat.BULLETIN, datetime(2026, 9, 26, 9, 0, tzinfo=UTC)),)
        at = datetime(2026, 9, 26, 9, 1, tzinfo=UTC)
        decision = decide(
            GridInputs(
                started, aired, at, UTC, {}, ALL, False, voices_by_format(4), None, failed=failed
            )
        )
        assert decision is None or decision.format is not RadioFormat.BULLETIN

    def test_a_failed_farewell_is_asked_for_again_at_once(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        stop_at = START + timedelta(minutes=10)
        failed = (AiredSegment(RadioFormat.SIGN_OFF, stop_at - timedelta(seconds=70)),)
        decision = decide(
            GridInputs(
                START,
                aired,
                stop_at - timedelta(seconds=60),
                UTC,
                {},
                ALL,
                False,
                voices_by_format(4),
                stop_at,
                failed=failed,
            )
        )
        assert decision is not None and decision.format is RadioFormat.SIGN_OFF


class TestClockMarksInRotation:
    def test_a_rotation_never_spends_the_bulletin_the_hour_is_about_to_air(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        # 08:55, the session runs past nine: the bulletin is kept for nine.
        i = inputs(aired=aired, air_at=START + timedelta(minutes=5))
        assert is_eligible(i, RadioFormat.BULLETIN) is False
        assert is_eligible(i, RadioFormat.COLUMN) is True

    def test_a_session_that_stops_before_the_hour_may_still_hear_a_bulletin(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        air_at = START + timedelta(minutes=2)  # 08:52
        i = inputs(aired=aired, air_at=air_at, stop_at=START + timedelta(minutes=9))  # 08:59
        assert is_eligible(i, RadioFormat.BULLETIN) is True

    def test_headlines_are_kept_for_twenty_past(self) -> None:
        started = datetime(2026, 9, 26, 8, 5, tzinfo=UTC)
        aired = (
            AiredSegment(RadioFormat.OPENING, started),
            AiredSegment(RadioFormat.JOURNAL, started),
        )
        at_ten_past = inputs(aired=aired, started=started, air_at=started + timedelta(minutes=5))
        assert is_eligible(at_ten_past, RadioFormat.HEADLINES) is False
        at_one_past = inputs(
            aired=aired,
            started=started - timedelta(minutes=5),
            air_at=started - timedelta(minutes=4),
        )
        assert is_eligible(at_one_past, RadioFormat.HEADLINES) is True

    def test_the_mark_itself_is_never_refused_by_its_own_rule(self) -> None:
        aired = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        decision = decide(inputs(aired=aired, air_at=datetime(2026, 9, 26, 9, 1, tzinfo=UTC)))
        assert decision is not None
        assert (decision.format, decision.reason) == (RadioFormat.BULLETIN, GridReason.TOP_OF_HOUR)


class TestNothingNew:
    """ADR-324 decision 38: said once a session, when the desk offers it — never drawn."""

    def test_the_station_says_it_once_when_the_listener_heard_it_all(self) -> None:
        opened = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        available = frozenset({RadioFormat.NOTHING_NEW, RadioFormat.BRIEF})
        first = decide(
            inputs(aired=opened, air_at=START + timedelta(minutes=3), available=available)
        )
        assert first is not None and first.format is RadioFormat.NOTHING_NEW
        said = (*opened, seg(RadioFormat.NOTHING_NEW, 3))
        again = decide(inputs(aired=said, air_at=START + timedelta(minutes=4), available=available))
        assert again is not None and again.format is not RadioFormat.NOTHING_NEW

    def test_it_is_never_drawn_while_there_is_news(self) -> None:
        opened = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        for minute in range(3, 40):
            chosen = decide(inputs(aired=opened, air_at=START + timedelta(minutes=minute)))
            assert chosen is None or chosen.format is not RadioFormat.NOTHING_NEW

    def test_a_listener_who_hears_no_news_is_never_told_there_is_nothing_new(self) -> None:
        opened = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        no_news = {
            fmt: Frequency.OFF
            for fmt, spec in FORMAT_SPECS.items()
            if spec.material is Material.NEWS and spec.user_selectable
        }
        chosen = decide(
            inputs(
                aired=opened,
                air_at=START + timedelta(minutes=3),
                frequencies=no_news,
                available=frozenset({RadioFormat.NOTHING_NEW, RadioFormat.BRIEF}),
            )
        )
        assert chosen is None or chosen.format is not RadioFormat.NOTHING_NEW

    def test_a_session_about_to_stop_says_goodbye_rather(self) -> None:
        opened = (seg(RadioFormat.OPENING, 0), seg(RadioFormat.JOURNAL, 1))
        air_at = START + timedelta(minutes=3)
        chosen = decide(
            inputs(
                aired=opened,
                air_at=air_at,
                available=frozenset({RadioFormat.NOTHING_NEW}),
                stop_at=air_at + timedelta(seconds=SIGN_OFF_WINDOW_SECONDS - 1),
            )
        )
        assert chosen is not None and chosen.format is RadioFormat.SIGN_OFF
