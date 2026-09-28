"""The antenna's grid: which programme airs next, decided without a model.

A pure function of what has aired, the clock, what the person asked for and what
there is to say. It never reads a database, never calls a provider and never
spends: it is the one place the station's rhythm lives, so it can be tested
minute by minute over a simulated day.

The rules, in the order they win:

1. an empty session opens with the OPENING;
2. when the automatic stop is close, the SIGN_OFF — and then nothing. This is
   the ONLY way a farewell is planned: never earlier than the window;
3. right after the opening, the listener's JOURNAL in the edition of the moment
   (:func:`~src.domains.radio.formats.journal_edition`, ADR-324 decision 41) —
   else the HEADLINES;
4. a bulletin at the top of the hour, headlines at twenty and forty past —
   announced as such only when the segment actually airs close to the mark;
5. the JOURNAL again, once the session crossed into another edition — or once
   it has something to say, when it had nothing at the start: an edition's
   journal airs ONCE, and two editions never come back to back (the format's
   own gap); then NOTHING_NEW, once, when the desk offers it (the listener heard
   every story left — decision 38): never drawn, the station's own word;
6. otherwise a weighted draw over what is enabled, available and allowed:
   never the same format twice in a row, never more briefs than the window
   allows, never a clock format spent in rotation when its own mark comes
   sooner than its minimum gap (a bulletin drawn at 8:50 would take the nine
   o'clock news from a session that will be listening at nine), never a
   personal format in public mode, never a format that needs more distinct
   voices than the cast holds, never one that would outlast the timer, never
   a format resting after a failed production — and never the journal, whose
   only doors are rules 3 and 5;
7. when that draw is empty, a FILL draw that relaxes spacing, the brief window
   and the clock marks — never the per-session bounds, public mode, the cast,
   the timer or a failure's rest. A different format wins whenever one fits;
   only without any eligible alternative may the previous format repeat.
   A station that falls silent sounds broken, and the fact-level ledger
   already keeps the CONTENT from repeating;
8. still nothing: nothing is planned. The station's music plays and the
   producer asks again; the farewell comes when rule 2 calls it. A station that
   said goodbye because nothing fitted was heard to stop minutes before its
   timer (measured 2026-09-26: nine minutes early on a thirty-minute stop, on
   durations projected at the formats' targets).

A format whose production FAILED rests (``FAILED_FORMAT_REST_SECONDS``, or its
own gap when longer) whatever rule would plan it — the clock rules included: a
failure is paid for, and the same attempt at once mostly fails the same way.
The opening and the farewell are exempt: the session cannot start without one
and cannot end without the other.

The ``air_at`` instant is when the planned segment will START (after what is
already queued), not the moment the grid is asked: a « top of the hour » decided
at 8:58 for a segment that airs at 9:01 is a bulletin.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import StrEnum
from typing import Final

from src.domains.radio.constants import (
    BRIEF_MAX_PER_WINDOW,
    BRIEF_WINDOW_SECONDS,
    FAILED_FORMAT_REST_SECONDS,
    HEADLINES_MARK_GRACE_SECONDS,
    HEADLINES_MARK_MINUTES,
    SIGN_OFF_WINDOW_SECONDS,
    STATION_ID_INTERVAL_SECONDS,
    TOP_OF_HOUR_GRACE_SECONDS,
)
from src.domains.radio.formats import (
    FORMAT_SPECS,
    FREQUENCY_WEIGHTS,
    Frequency,
    JournalEdition,
    Material,
    RadioFormat,
    journal_edition,
)

#: The minutes past the hour each clock format airs at, on the person's clock.
_CLOCK_MARKS: Final[dict[RadioFormat, tuple[int, ...]]] = {
    RadioFormat.BULLETIN: (0,),
    RadioFormat.HEADLINES: HEADLINES_MARK_MINUTES,
}


def _utc(value: datetime, name: str) -> datetime:
    """The instant in UTC; a naive datetime is refused, never guessed.

    Every interval the grid measures (gaps, windows, the timer) is a
    difference of instants. Normalised here once, no subtraction below can fall
    into the wall-clock trap of two datetimes sharing a local ``tzinfo``.
    """
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class GridReason(StrEnum):
    """Why the grid chose what it chose — a bounded label for logs and metrics."""

    OPENING = "opening"
    SIGN_OFF = "sign_off"
    DAY_START = "day_start"
    TOP_OF_HOUR = "top_of_hour"
    HEADLINES_MARK = "headlines_mark"
    JOURNAL_EDITION = "journal_edition"
    NOTHING_NEW = "nothing_new"
    ROTATION = "rotation"
    FILL = "fill"


@dataclass(frozen=True, slots=True)
class AiredSegment:
    """One segment of the session, planned or played.

    Attributes:
        format: What it was.
        air_at: When it started (or will start), timezone-aware.
        station_id: Whether it named the station.
    """

    format: RadioFormat
    air_at: datetime
    station_id: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "air_at", _utc(self.air_at, "air_at"))


@dataclass(frozen=True, slots=True)
class GridInputs:
    """Everything the grid needs to decide the next segment.

    Attributes:
        session_started_at: When the session began (aware).
        aired: The session's segments so far, in air order.
        air_at: When the NEXT segment will start (aware).
        timezone: The person's timezone — the clock marks are local.
        frequencies: The person's choice per format (missing = the default).
        available: Formats that have something to say right now.
        public_mode: No personal format may air.
        voices_by_format: How many distinct voices each programme's roles
            are heard with (a dialogue needs two, a debate three; a missing
            programme has none).
        stop_at: The automatic stop, or ``None`` for no stop.
        failed: The session's failed productions — each format with the
            instant it failed at (a format rests after one).
    """

    session_started_at: datetime
    aired: tuple[AiredSegment, ...]
    air_at: datetime
    timezone: tzinfo
    frequencies: Mapping[RadioFormat, Frequency]
    available: frozenset[RadioFormat]
    public_mode: bool
    voices_by_format: Mapping[RadioFormat, int]
    stop_at: datetime | None
    failed: tuple[AiredSegment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "session_started_at", _utc(self.session_started_at, "session_started_at")
        )
        object.__setattr__(self, "air_at", _utc(self.air_at, "air_at"))
        if self.stop_at is not None:
            object.__setattr__(self, "stop_at", _utc(self.stop_at, "stop_at"))


@dataclass(frozen=True, slots=True)
class GridDecision:
    """What airs next, and why.

    Attributes:
        format: The chosen format.
        reason: Why this one (bounded vocabulary).
        station_id_due: Whether its intro should name the station.
        clock_mark: The local instant the segment is announced for (« the
            nine o'clock news »), when a clock rule chose it.
    """

    format: RadioFormat
    reason: GridReason
    station_id_due: bool
    clock_mark: datetime | None = None


def frequency_of(inputs: GridInputs, fmt: RadioFormat) -> Frequency:
    """The person's frequency for ``fmt``, or the format's default."""
    return inputs.frequencies.get(fmt, FORMAT_SPECS[fmt].default_frequency)


def _count(inputs: GridInputs, fmt: RadioFormat) -> int:
    return sum(1 for seg in inputs.aired if seg.format is fmt)


def _last_air(inputs: GridInputs, fmt: RadioFormat) -> datetime | None:
    times = [seg.air_at for seg in inputs.aired if seg.format is fmt]
    return max(times) if times else None


def _seconds_left(inputs: GridInputs) -> float | None:
    if inputs.stop_at is None:
        return None
    return (inputs.stop_at - inputs.air_at).total_seconds()


def _briefs_in_window(inputs: GridInputs) -> int:
    since = inputs.air_at - timedelta(seconds=BRIEF_WINDOW_SECONDS)
    return sum(1 for s in inputs.aired if s.format is RadioFormat.BRIEF and s.air_at > since)


def _edition_of(inputs: GridInputs, instant: datetime) -> tuple[date, JournalEdition]:
    """The journal's edition ``instant`` falls in, on the listener's clock.

    The local DAY comes with it: a session that runs past midnight hears the next
    day's morning edition, not « the morning's again ».
    """
    local = instant.astimezone(inputs.timezone)
    return local.date(), journal_edition(local)


def _journal_aired_this_edition(inputs: GridInputs) -> bool:
    """Whether the edition the next segment falls in already had its journal."""
    edition = _edition_of(inputs, inputs.air_at)
    return any(
        seg.format is RadioFormat.JOURNAL and _edition_of(inputs, seg.air_at) == edition
        for seg in inputs.aired
    )


def _wanted(inputs: GridInputs, fmt: RadioFormat) -> bool:
    """What the person and the moment allow: chosen, available, not private in public."""
    spec = FORMAT_SPECS[fmt]
    if not spec.user_selectable or frequency_of(inputs, fmt) is Frequency.OFF:
        return False
    if fmt not in inputs.available:
        return False
    if inputs.public_mode and spec.material is Material.PERSONAL:
        return False
    return spec.min_distinct_voices <= inputs.voices_by_format.get(fmt, 0)


def _rests(inputs: GridInputs, fmt: RadioFormat) -> bool:
    """Whether ``fmt`` failed too recently to be planned again."""
    failures = [seg.air_at for seg in inputs.failed if seg.format is fmt]
    if not failures:
        return False
    rest = max(FAILED_FORMAT_REST_SECONDS, FORMAT_SPECS[fmt].min_gap_seconds)
    return (inputs.air_at - max(failures)).total_seconds() < rest


def _fits_session(inputs: GridInputs, fmt: RadioFormat, *, varied: bool = True) -> bool:
    """What the session allows: the per-session bounds, the timer, a failure's rest, variety.

    The journal's bound is per EDITION of the listener's day (decision 41) — a
    session bound like the others, never relaxed.

    Args:
        inputs: The grid's inputs.
        fmt: The candidate.
        varied: Whether the variety rules (twice in a row, minimum gap, brief
            window) apply — relaxed by the FILL draw alone.
    """
    spec = FORMAT_SPECS[fmt]
    if spec.max_per_session is not None and _count(inputs, fmt) >= spec.max_per_session:
        return False
    if fmt is RadioFormat.JOURNAL and _journal_aired_this_edition(inputs):
        return False
    if _rests(inputs, fmt):
        return False
    if varied and not _varied(inputs, fmt):
        return False
    left = _seconds_left(inputs)
    return left is None or spec.target_seconds + SIGN_OFF_WINDOW_SECONDS <= left


def _seconds_to_own_mark(inputs: GridInputs, fmt: RadioFormat) -> float | None:
    """Seconds from the next air time to the next clock mark ``fmt`` airs for.

    Counted on the local clock's minutes and seconds, not by building the mark:
    an hour of the wall clock is an hour of real time on both sides of a
    change, and no instant has to be constructed in a gap or a fold.
    """
    marks = _CLOCK_MARKS.get(fmt)
    if marks is None:
        return None
    local = inputs.air_at.astimezone(inputs.timezone)
    into_hour = local.minute * 60 + local.second + local.microsecond / 1_000_000
    return min(((minute * 60 - into_hour) % 3600) or 3600.0 for minute in marks)


def _keeps_its_mark(inputs: GridInputs, fmt: RadioFormat) -> bool:
    """Whether airing ``fmt`` now leaves its next clock mark free.

    A clock format drawn in rotation closer to its mark than its minimum gap
    would make the mark itself refused — unless the session stops first.
    """
    ahead = _seconds_to_own_mark(inputs, fmt)
    if ahead is None or ahead >= FORMAT_SPECS[fmt].min_gap_seconds:
        return True
    left = _seconds_left(inputs)
    return left is not None and left <= ahead


def _varied(inputs: GridInputs, fmt: RadioFormat) -> bool:
    """The variety rules: not twice in a row, the gap, the brief window, the clock."""
    if inputs.aired and inputs.aired[-1].format is fmt:
        return False
    last = _last_air(inputs, fmt)
    gap = FORMAT_SPECS[fmt].min_gap_seconds
    if last is not None and (inputs.air_at - last).total_seconds() < gap:
        return False
    if fmt is RadioFormat.BRIEF and _briefs_in_window(inputs) >= BRIEF_MAX_PER_WINDOW:
        return False
    return _keeps_its_mark(inputs, fmt)


def is_eligible(inputs: GridInputs, fmt: RadioFormat) -> bool:
    """Whether ``fmt`` may air next — every constraint but the clock rules.

    Args:
        inputs: The grid's inputs.
        fmt: The candidate.

    Returns:
        True when nothing forbids it.
    """
    return _wanted(inputs, fmt) and _fits_session(inputs, fmt)


def _station_id_due(inputs: GridInputs) -> bool:
    named = [seg.air_at for seg in inputs.aired if seg.station_id]
    last = max(named) if named else None
    if last is None:
        return True
    return (inputs.air_at - last).total_seconds() >= STATION_ID_INTERVAL_SECONDS


def _after_start_and_unserved(
    inputs: GridInputs, mark: datetime, formats: tuple[RadioFormat, ...]
) -> bool:
    """Whether a clock mark falls inside the session and nothing honoured it yet.

    The mark is local; it is compared in UTC with the stored instants (already
    UTC): two datetimes sharing one local ``tzinfo`` compare on their WALL
    clocks, which misorders the repeated hour of a clock change (ADR-318).
    """
    mark_utc = mark.astimezone(UTC)
    if mark_utc <= inputs.session_started_at:
        return False
    for fmt in formats:
        last = _last_air(inputs, fmt)
        if last is not None and last >= mark_utc:
            return False
    return True


def _top_of_hour(inputs: GridInputs) -> datetime | None:
    """The local top of the hour the next segment would honour, if any."""
    local = inputs.air_at.astimezone(inputs.timezone)
    mark = local.replace(minute=0, second=0, microsecond=0)
    # Minutes past the hour on the local clock: a wall-clock difference is the
    # meaning here, and ``mark`` shares ``local``'s hour and fold.
    if (local - mark).total_seconds() > TOP_OF_HOUR_GRACE_SECONDS:
        return None
    if not _after_start_and_unserved(inputs, mark, (RadioFormat.BULLETIN,)):
        return None
    return mark


def _headlines_mark(inputs: GridInputs) -> datetime | None:
    """The twenty-past or forty-past mark the next segment would honour, if any."""
    local = inputs.air_at.astimezone(inputs.timezone)
    marks = [m for m in HEADLINES_MARK_MINUTES if m <= local.minute]
    if not marks:
        return None
    mark = local.replace(minute=max(marks), second=0, microsecond=0)
    if (local - mark).total_seconds() > HEADLINES_MARK_GRACE_SECONDS:
        return None
    if not _after_start_and_unserved(inputs, mark, (RadioFormat.HEADLINES, RadioFormat.BULLETIN)):
        return None
    return mark


def _decide(inputs: GridInputs, fmt: RadioFormat, reason: GridReason) -> GridDecision:
    return GridDecision(format=fmt, reason=reason, station_id_due=_station_id_due(inputs))


def _forced(inputs: GridInputs) -> GridDecision | None:
    """The rules that win over the draw, in order."""
    if len(inputs.aired) == 1:
        for fmt in (RadioFormat.JOURNAL, RadioFormat.HEADLINES):
            if is_eligible(inputs, fmt):
                return _decide(inputs, fmt, GridReason.DAY_START)
    hour_mark = _top_of_hour(inputs)
    if hour_mark is not None and is_eligible(inputs, RadioFormat.BULLETIN):
        decision = _decide(inputs, RadioFormat.BULLETIN, GridReason.TOP_OF_HOUR)
        return GridDecision(decision.format, decision.reason, decision.station_id_due, hour_mark)
    headlines_mark = _headlines_mark(inputs)
    if headlines_mark is not None and is_eligible(inputs, RadioFormat.HEADLINES):
        decision = _decide(inputs, RadioFormat.HEADLINES, GridReason.HEADLINES_MARK)
        return GridDecision(
            decision.format, decision.reason, decision.station_id_due, headlines_mark
        )
    # Eligible means: something to say, and no journal yet in this edition (rule 5).
    if is_eligible(inputs, RadioFormat.JOURNAL):
        return _decide(inputs, RadioFormat.JOURNAL, GridReason.JOURNAL_EDITION)
    if (
        RadioFormat.NOTHING_NEW in inputs.available
        and _hears_news(inputs)
        and _fits_session(inputs, RadioFormat.NOTHING_NEW, varied=False)
    ):
        return _decide(inputs, RadioFormat.NOTHING_NEW, GridReason.NOTHING_NEW)
    return None


def _hears_news(inputs: GridInputs) -> bool:
    """Whether the listener hears a news programme: « nothing new » is no news to one who
    switched every one of them off."""
    return any(
        spec.material is Material.NEWS
        and spec.user_selectable
        and frequency_of(inputs, fmt) is not Frequency.OFF
        for fmt, spec in FORMAT_SPECS.items()
    )


def next_segment(inputs: GridInputs, rng: random.Random) -> GridDecision | None:
    """Decide the next segment, or ``None`` when there is nothing to air.

    Args:
        inputs: The grid's inputs.
        rng: The draw's source — seeded by the caller so a session is replayable.

    Returns:
        The decision, or ``None`` after the sign-off, or when nothing fits
        yet even with variety relaxed — the station's music plays, and the
        producer asks again (with a timer, rule 2 calls the farewell once the
        window opens).
    """
    if not inputs.aired:
        return GridDecision(RadioFormat.OPENING, GridReason.OPENING, station_id_due=True)
    if any(seg.format is RadioFormat.SIGN_OFF for seg in inputs.aired):
        return None
    left = _seconds_left(inputs)
    if left is not None and left <= SIGN_OFF_WINDOW_SECONDS:
        return _decide(inputs, RadioFormat.SIGN_OFF, GridReason.SIGN_OFF)

    forced = _forced(inputs)
    if forced is not None:
        return forced
    return _draw(inputs, rng)


def _draw(inputs: GridInputs, rng: random.Random) -> GridDecision | None:
    """Rules 6 to 8: the weighted draw, the FILL draw, then nothing (the music plays)."""
    for varied, reason in ((True, GridReason.ROTATION), (False, GridReason.FILL)):
        candidates = [
            fmt
            for fmt in FORMAT_SPECS
            if fmt is not RadioFormat.JOURNAL
            and _wanted(inputs, fmt)
            and _fits_session(inputs, fmt, varied=varied)
        ]
        if candidates:
            # Even FILL changes programme when it can. Frequencies weight the
            # alternatives; they never buy a repeat while another format fits.
            candidates = [
                fmt for fmt in candidates if fmt is not inputs.aired[-1].format
            ] or candidates
            weights = [FREQUENCY_WEIGHTS[frequency_of(inputs, fmt)] for fmt in candidates]
            chosen = rng.choices(candidates, weights=weights, k=1)[0]
            return _decide(inputs, chosen, reason)
    return None
