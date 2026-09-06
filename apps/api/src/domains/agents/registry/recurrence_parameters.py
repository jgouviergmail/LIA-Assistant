"""The spoken recurrence vocabulary, declared once for every tool that takes it.

Two tools ask a reader the same questions — which days, at what times, how
often, until when — so they ask them with the same words. One declaration
here, read by both signatures and both manifests, is what stops the two from
drifting into dialects of each other.

**The bounds travel with the caller** (ADR-184). A routine may fire 12 times a
day and a reminder 48; the numbers in the manifest are therefore built from the
consumer's own `RecurrenceLimits`, never from a constant here. A bound the
planner cannot see is a trap, not a contract — and a bound it sees that the
validator does not enforce is worse.

Descriptions are technical English (ADR-256): the model reformulates in the
reader's language, and a French description would make the two execution modes
speak differently about the same parameter.
"""

from __future__ import annotations

from src.core.recurrence import (
    CLOCK_PATTERN,
    DATE_PATTERN,
    NTH_WEEKDAY_PATTERN,
    REPEAT_VALUES,
    RecurrenceLimits,
)
from src.domains.agents.registry.catalogue import ParameterConstraint, ParameterSchema

#: Every description, in one place, so a tool's `Annotated` metadata and its
#: manifest entry cannot disagree about what a parameter means.
RECURRENCE_DOCS: dict[str, str] = {
    "repeat": (
        "How the schedule walks the calendar: 'once' (a single firing), "
        "'daily', 'weekly', 'monthly' or 'yearly'. "
        # A schedule is not a guess. "Remind me often" or "from time to time"
        # names no frequency, and choosing one silently commits the reader to
        # a rhythm they never asked for — on a capability that then acts on
        # its own, every day, until they notice. ASKING is the cheap move and
        # it belongs here, where the producer reads (ADR-184): a rule the
        # model cannot see is a rule it cannot follow.
        "If the request names no clear rhythm ('often', 'from time to time', "
        "'regularly'), ASK the reader which one they mean instead of choosing "
        "for them."
    ),
    "times": (
        "Times of day as 'HH:MM' on a 24-hour clock, one per firing. "
        "Several values mean several firings the SAME day "
        "(e.g. ['08:00','18:00'] for morning and evening)."
    ),
    "repeat_every": (
        "One period out of N: 2 with repeat='weekly' is every other week, "
        "3 with repeat='daily' is every three days. Default 1."
    ),
    "weekdays": (
        "repeat='weekly': ISO weekdays, 1=Monday .. 7=Sunday. "
        "[1,2,3,4,5] is weekdays, [6,7] is the weekend."
    ),
    "month_days": (
        "repeat='monthly' or 'yearly': days of the month, 1..31, "
        "or -1 for the LAST day. A month too short simply skips."
    ),
    "months": "repeat='yearly': months, 1=January .. 12=December.",
    "nth_weekday": (
        "repeat='monthly', for 'the 2nd Tuesday' rather than a fixed day: "
        "'<nth>:<weekday>' with nth in 1..5 or -1 for the last, and weekday "
        "1=Monday. '2:2' is the second Tuesday. Not with month_days."
    ),
    "every_minutes": (
        "Instead of `times`: fire every N minutes inside a window. "
        "Requires window_start and window_end."
    ),
    "window_start": "First time of the stepped window, 'HH:MM'.",
    "window_end": "Last time of the stepped window, 'HH:MM'.",
    "until_date": (
        "The LAST day the schedule serves, 'YYYY-MM-DD', included. " "Not with max_occurrences."
    ),
    "max_occurrences": (
        "How many FIRINGS the schedule holds in total (not days), counted from "
        "`starting_on`. For 'the next N times', set starting_on to the first "
        "day whose time has not passed yet. Not with until_date."
    ),
    "starting_on": (
        "The day the schedule starts, 'YYYY-MM-DD'. It is also the PHASE when "
        "repeat_every is above 1: 'every other Tuesday' needs to know which "
        "Tuesday. Defaults to today."
    ),
}


def recurrence_parameters(
    limits: RecurrenceLimits, *, repeat_required: bool
) -> list[ParameterSchema]:
    """The recurrence parameters, bounded by what THIS consumer allows.

    Args:
        limits: The caller's own ceilings. Their numbers become the published
            `minimum`/`maximum`, so the planner reads the bound the validator
            will apply rather than a shared approximation.
        repeat_required: True for a tool whose whole subject is a schedule (a
            routine), False for one where a schedule is one way of speaking
            among others (a reminder, which also takes a single instant).

    Returns:
        The parameter schemas, in the order a reader answers them.
    """
    return [
        ParameterSchema(
            name="repeat",
            type="string",
            required=repeat_required,
            description=RECURRENCE_DOCS["repeat"],
            constraints=[ParameterConstraint(kind="enum", value=list(REPEAT_VALUES))],
        ),
        ParameterSchema(
            name="times",
            type="array",
            required=False,
            description=RECURRENCE_DOCS["times"],
            constraints=[ParameterConstraint(kind="max_length", value=limits.max_times_per_day)],
        ),
        ParameterSchema(
            name="repeat_every",
            type="integer",
            required=False,
            description=RECURRENCE_DOCS["repeat_every"],
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=999),
            ],
        ),
        ParameterSchema(
            name="weekdays",
            type="array",
            required=False,
            description=RECURRENCE_DOCS["weekdays"],
            constraints=[ParameterConstraint(kind="max_length", value=7)],
        ),
        ParameterSchema(
            name="month_days",
            type="array",
            required=False,
            description=RECURRENCE_DOCS["month_days"],
            constraints=[ParameterConstraint(kind="max_length", value=31)],
        ),
        ParameterSchema(
            name="months",
            type="array",
            required=False,
            description=RECURRENCE_DOCS["months"],
            constraints=[ParameterConstraint(kind="max_length", value=12)],
        ),
        ParameterSchema(
            name="nth_weekday",
            type="string",
            required=False,
            description=RECURRENCE_DOCS["nth_weekday"],
            constraints=[ParameterConstraint(kind="pattern", value=NTH_WEEKDAY_PATTERN)],
        ),
        ParameterSchema(
            name="every_minutes",
            type="integer",
            required=False,
            description=RECURRENCE_DOCS["every_minutes"],
            constraints=[
                ParameterConstraint(kind="minimum", value=limits.min_step_minutes),
                ParameterConstraint(kind="maximum", value=1440),
            ],
        ),
        ParameterSchema(
            name="window_start",
            type="string",
            required=False,
            description=RECURRENCE_DOCS["window_start"],
            constraints=[ParameterConstraint(kind="pattern", value=CLOCK_PATTERN)],
        ),
        ParameterSchema(
            name="window_end",
            type="string",
            required=False,
            description=RECURRENCE_DOCS["window_end"],
            constraints=[ParameterConstraint(kind="pattern", value=CLOCK_PATTERN)],
        ),
        ParameterSchema(
            name="until_date",
            type="string",
            required=False,
            description=RECURRENCE_DOCS["until_date"],
            constraints=[ParameterConstraint(kind="pattern", value=DATE_PATTERN)],
        ),
        ParameterSchema(
            name="max_occurrences",
            type="integer",
            required=False,
            description=RECURRENCE_DOCS["max_occurrences"],
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=limits.max_series_count),
            ],
        ),
        ParameterSchema(
            name="starting_on",
            type="string",
            required=False,
            description=RECURRENCE_DOCS["starting_on"],
            constraints=[ParameterConstraint(kind="pattern", value=DATE_PATTERN)],
        ),
    ]
