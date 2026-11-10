"""Measure the usage proposals on simulated people — a MEASUREMENT, never a gate.

ADR-375 replaced the « same request at the same hour » lock with recurring
NEEDS and six kinds of PROPOSAL. Their bars were calibrated on simulated people
before they shipped; this script is that simulation, kept in the repository,
and it runs the REAL code every night of a simulated month:
``usage_observations.needs_from_ledger`` (``needs.detect_need``) and
``proposal_rules.evaluate_proposals``.

A persona says WHAT a person does, never at a fixed hour: hours are drawn from
wide distributions, days are skipped, ad hoc requests mix in. Each carries the
proposals a reasonable observer would expect of it, and those that observer
would call DEFENSIBLE without expecting them (a daily routine for someone who
also reads their mail on some weekends). Over many seeds the report shows how
often each expected proposal is open on the last night and the median night it
first opened, each defensible one's rate apart, and every other proposal that
opened: the false positives this tool exists to make VISIBLE. Lowering a bar
until a persona « passes » hides that cost; it never removes it.

An automation is identified with its cadence (``automate_need:email@weekdays``):
a need detected at the wrong cadence reads as one expectation missed and one
proposal unexpected.

The bars are the SHIPPED ``*_DEFAULT`` constants, never the live settings:
under ``task`` the root .env is injected, and an operator's override would
silently become the measured calibration (``measure_calibration.py`` closes the
same trap). People, domains and hours are invented; no record of any instance
is read.

Usage (from apps/api, through task: the engine's imports need the settings the
root .env provides):
    task habits:proposals:measure
    task habits:proposals:measure -- --seeds 300 --persona weekly_planner
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.core import constants as C  # noqa: E402
from src.domains.habits.models import ProposalKind  # noqa: E402
from src.domains.habits.needs import NeedThresholds  # noqa: E402
from src.domains.habits.proposal_rules import (  # noqa: E402
    ProactiveFeedback,
    ProposalCandidate,
    ProposalThresholds,
    RoutineRun,
    RoutineView,
    UsageObservations,
    evaluate_proposals,
)
from src.domains.habits.usage_observations import LedgerView, needs_from_ledger  # noqa: E402

SHIPPED = SimpleNamespace(
    recurrence_window_days=C.RECURRENCE_WINDOW_DAYS_DEFAULT,
    recurrence_min_distinct_days=C.RECURRENCE_MIN_DISTINCT_DAYS_DEFAULT,
    recurrence_need_min_weeks=C.RECURRENCE_NEED_MIN_WEEKS_DEFAULT,
    recurrence_need_recent_days=C.RECURRENCE_NEED_RECENT_DAYS_DEFAULT,
    recurrence_automate_share=C.RECURRENCE_AUTOMATE_SHARE_DEFAULT,
    recurrence_automate_min_days=C.RECURRENCE_AUTOMATE_MIN_DAYS_DEFAULT,
    recurrence_weekly_min_same_dow=C.RECURRENCE_WEEKLY_MIN_SAME_DOW_DEFAULT,
    recurrence_weekly_dow_fraction=C.RECURRENCE_WEEKLY_DOW_FRACTION_DEFAULT,
    recurrence_weekend_tolerance=C.RECURRENCE_WEEKEND_TOLERANCE_DEFAULT,
    recurrence_part_of_day_share=C.RECURRENCE_PART_OF_DAY_SHARE_DEFAULT,
    habits_proposal_routine_gap_hours=C.HABITS_PROPOSAL_ROUTINE_GAP_HOURS_DEFAULT,
    habits_proposal_manual_min_runs=C.HABITS_PROPOSAL_MANUAL_MIN_RUNS_DEFAULT,
    habits_proposal_manual_min_days=C.HABITS_PROPOSAL_MANUAL_MIN_DAYS_DEFAULT,
    habits_proposal_failure_streak=C.HABITS_PROPOSAL_FAILURE_STREAK_DEFAULT,
    habits_proposal_window_min_days=C.HABITS_PROPOSAL_WINDOW_MIN_DAYS_DEFAULT,
    habits_proposal_window_min_cells=C.HABITS_PROPOSAL_WINDOW_MIN_CELLS_DEFAULT,
    habits_proposal_window_min_share=C.HABITS_PROPOSAL_WINDOW_MIN_SHARE_DEFAULT,
    habits_proposal_window_max_extension_hours=C.HABITS_PROPOSAL_WINDOW_MAX_EXTENSION_HOURS_DEFAULT,
    habits_proposal_silent_min_notifications=C.HABITS_PROPOSAL_SILENT_MIN_NOTIFICATIONS_DEFAULT,
    habits_proposal_connector_min_days=C.HABITS_PROPOSAL_CONNECTOR_MIN_DAYS_DEFAULT,
    habits_proposal_mute_after_refusals=C.HABITS_PROPOSAL_MUTE_AFTER_REFUSALS_DEFAULT,
)
NEED_BARS = NeedThresholds.from_settings(SHIPPED)
PROPOSAL_BARS = ProposalThresholds.from_settings(SHIPPED)
NOTIFY_WINDOW = (C.HEARTBEAT_NOTIFY_START_HOUR_DEFAULT, C.HEARTBEAT_NOTIFY_END_HOUR_DEFAULT)

START = date(2026, 10, 5)  # a Monday; the month simulated is fixed, its days are not
WINDOW_DAYS = NEED_BARS.window_days  # what the nightly job reads, whatever is simulated
NIGHTS = WINDOW_DAYS  # one full window by default
SEEDS = 100
CONNECTED = frozenset({"calendar", "email", "tasks", "contacts"})
EVERYTHING = frozenset({"calendar", "email", "tasks", "contacts", "files", "telephony"})


@dataclass
class Routine:
    """A time routine of the persona: one scheduled hour, every day, known reads."""

    id: str
    title: str
    hour: float
    reads: frozenset[str]
    runs: list[RoutineRun] = field(default_factory=list)


@dataclass
class Life:
    """What one simulated person did, day by day."""

    asks: dict[str, dict[date, list[float]]] = field(default_factory=dict)
    presence: dict[date, set[int]] = field(default_factory=dict)
    notifications: list[tuple[date, bool]] = field(default_factory=list)
    routines: list[Routine] = field(default_factory=list)
    connectors: frozenset[str] = CONNECTED
    heartbeat: bool = False


def _hour(rng: random.Random, mean: float, sd: float, lo: float = 5.0, hi: float = 23.9) -> float:
    return min(hi, max(lo, rng.gauss(mean, sd)))


def _ask(life: Life, day: date, hour: float, domain: str) -> None:
    """One ask, kept as the ledger keeps it: one entry per clock hour per day."""
    hour = min(hour, 23.99)  # a local hour the ledger records is always before midnight
    hours = life.asks.setdefault(domain, {}).setdefault(day, [])
    if int(hour) not in {int(h) for h in hours}:
        hours.append(hour)
    life.presence.setdefault(day, set()).add(int(hour) % 24)


def _browse(life: Life, rng: random.Random, day: date, p: float = 0.5, mean: float = 15) -> None:
    """An app opening with no request: presence only."""
    if rng.random() < p:
        life.presence.setdefault(day, set()).add(int(_hour(rng, mean, 4)))


def _adhoc(
    life: Life,
    rng: random.Random,
    day: date,
    pool: Sequence[str] = ("web_search", "place", "wikipedia", "route"),
) -> None:
    """Requests that are nobody's habit: a varied search, a place, a route."""
    for _ in range(rng.choices([0, 1, 2, 3], weights=[0.45, 0.3, 0.17, 0.08])[0]):
        _ask(life, day, _hour(rng, 14, 4.5), rng.choice(pool))


def _run(routine: Routine, day: date, hour: float, *, manual: bool) -> None:
    routine.runs.append(RoutineRun(day, hour, manual, "success", f"run-{day}-{hour:.2f}"))


# ---------------------------------------------------------------------------
# Personas: what a person does on day ``i`` (never at a fixed hour)
# ---------------------------------------------------------------------------


def evening_agenda(life: Life, rng: random.Random, day: date, _i: int) -> None:
    if rng.random() < 0.75:
        _ask(life, day, _hour(rng, 20.5, 1.3), "event")
    elif rng.random() < 0.3:
        _ask(life, day, _hour(rng, 8.5, 1.0), "event")
    if rng.random() < 0.2:
        _ask(life, day, _hour(rng, 12, 4), "weather")
    _adhoc(life, rng, day)
    _browse(life, rng, day)


def workday_mail(life: Life, rng: random.Random, day: date, _i: int) -> None:
    if day.weekday() < 5:
        if rng.random() < 0.85:
            _ask(life, day, _hour(rng, 8.7, 0.9), "email")
        if rng.random() < 0.35:
            _ask(life, day, _hour(rng, 15, 2), "email")
    elif rng.random() < 0.1:
        _ask(life, day, _hour(rng, 11, 2), "email")
    _adhoc(life, rng, day, ("web_search", "place"))
    _browse(life, rng, day, p=0.3)


def explorer(life: Life, rng: random.Random, day: date, _i: int) -> None:
    for _ in range(rng.choice([1, 2, 3, 4, 5])):
        _ask(life, day, _hour(rng, 15, 4.5), rng.choice(["web_search", "wikipedia", "place"]))
    if day.weekday() == rng.choice([0, 6]) and rng.random() < 0.6:
        _ask(life, day, _hour(rng, 19, 2), "event")
    _browse(life, rng, day, p=0.6)


def same_search(life: Life, rng: random.Random, day: date, _i: int) -> None:
    """The same web search most days: a need, but not one a routine sums up (v1)."""
    if rng.random() < 0.6:
        _ask(life, day, _hour(rng, 9, 3.5), "web_search")
    _adhoc(life, rng, day, ("web_search", "wikipedia"))
    _browse(life, rng, day, p=0.3)


def relauncher(life: Life, rng: random.Random, day: date, i: int) -> None:
    if i == 0:
        life.routines.append(Routine("r1", "Morning", 6.0, frozenset({"email", "event"})))
    routine = life.routines[0]
    _run(routine, day, 6.0 + rng.random() * 0.2, manual=False)
    if rng.random() < 0.4:
        manual_hour = _hour(rng, 10, 1.0)
        _run(routine, day, manual_hour, manual=True)
        life.presence.setdefault(day, set()).add(int(manual_hour))
    _adhoc(life, rng, day, ("web_search",))
    _browse(life, rng, day, p=0.4)


def night_owl(life: Life, rng: random.Random, day: date, _i: int) -> None:
    life.heartbeat = True
    if rng.random() < 0.8:
        life.presence.setdefault(day, set()).update(
            rng.sample([22, 23, 0, 1], k=rng.choice([1, 2, 3]))
        )
    if rng.random() < 0.5:
        _ask(life, day, _hour(rng, 23, 1.0, lo=20.0), rng.choice(["web_search", "event"]))
    _browse(life, rng, day, p=0.5, mean=13)
    if rng.random() < 0.4:
        life.notifications.append((day, False))


def silent(life: Life, rng: random.Random, day: date, _i: int) -> None:
    life.heartbeat = True
    life.notifications.append((day, False))
    if rng.random() < 0.3:
        _ask(life, day, _hour(rng, 12, 4), rng.choice(["web_search", "weather"]))
    _browse(life, rng, day, p=0.3)


def engaged(life: Life, rng: random.Random, day: date, _i: int) -> None:
    life.heartbeat = True
    life.notifications.append((day, rng.random() < 0.3))
    if rng.random() < 0.5:
        _ask(life, day, _hour(rng, 9, 2), "event")
    _browse(life, rng, day)


def sparse(life: Life, rng: random.Random, day: date, _i: int) -> None:
    if rng.random() < 0.2:
        _ask(life, day, _hour(rng, 14, 5), rng.choice(["web_search", "event", "email", "weather"]))


def no_connector(life: Life, rng: random.Random, day: date, _i: int) -> None:
    life.connectors = frozenset({"calendar"})
    if rng.random() < 0.3:
        _ask(life, day, _hour(rng, 10, 3), "email")
    if rng.random() < 0.5:
        _ask(life, day, _hour(rng, 10, 3), "event")
    _browse(life, rng, day, p=0.4)


def weekly_planner(life: Life, rng: random.Random, day: date, _i: int) -> None:
    if day.weekday() == 6 and rng.random() < 0.9:
        _ask(life, day, _hour(rng, 19.5, 1.2), "event")
        _ask(life, day, _hour(rng, 19.8, 1.2), "task")
    if rng.random() < 0.3:
        _ask(life, day, _hour(rng, 14, 4.5), "web_search")
    _browse(life, rng, day, p=0.2)


def drifting(life: Life, rng: random.Random, day: date, i: int) -> None:
    """A need that stopped: asked the first two weeks, never again."""
    if i < 14 and rng.random() < 0.8:
        _ask(life, day, _hour(rng, 9, 2.5), "event")
    if rng.random() < 0.3:
        _ask(life, day, _hour(rng, 14, 4.5), "web_search")
    _browse(life, rng, day, p=0.3)


def bench(life: Life, rng: random.Random, day: date, i: int) -> None:
    """A tester: agenda and mail most days at any hour, a morning routine, everything on."""
    if i == 0:
        life.connectors = EVERYTHING
        life.heartbeat = True
        life.routines.append(
            Routine("morning", "Briefing", 7.75, frozenset({"email", "event", "task"}))
        )
    _run(life.routines[0], day, 7.75, manual=False)
    if rng.random() < 0.6:
        for _ in range(rng.choice([1, 2, 3])):
            hour = _hour(rng, 14, 5)
            _ask(life, day, hour, "event")
            if rng.random() < 0.6:
                _ask(life, day, hour + 0.1, "email")
    for _ in range(rng.choice([0, 1, 2, 4])):
        domain = rng.choice(
            ["place", "route", "image_generation", "web_search", "telephony", "weather"]
        )
        _ask(life, day, _hour(rng, 16, 5), domain)
    life.presence.setdefault(day, set()).update(rng.sample(range(24), k=rng.choice([2, 4, 6])))
    life.notifications += [(day, False), (day, False)]


@dataclass(frozen=True, slots=True)
class Persona:
    """A generative person and the proposals a reasonable observer expects of them.

    Attributes:
        name: The persona.
        live: What they do on one day.
        expected: The proposals an observer expects.
        defensible: Proposals the observer would not expect, nor call wrong:
            reported apart, never counted as a false positive nor as a hit.
    """

    name: str
    live: Callable[[Life, random.Random, date, int], None]
    expected: frozenset[str]
    defensible: frozenset[str] = frozenset()


PERSONAS: tuple[Persona, ...] = (
    Persona(
        "evening_agenda",
        evening_agenda,
        frozenset({"automate_need:event@daily"}),
        # The weather asked on a fifth of the days reaches the bar in a few months.
        defensible=frozenset({"automate_need:weather@daily"}),
    ),
    Persona(
        "workday_mail",
        workday_mail,
        frozenset({"automate_need:email@weekdays"}),
        # Two weekend reads in the month make the week whole: a daily routine.
        defensible=frozenset({"automate_need:email@daily"}),
    ),
    Persona("explorer", explorer, frozenset()),
    Persona("same_search", same_search, frozenset()),
    Persona("relauncher", relauncher, frozenset({"shift_routine:r1"})),
    Persona(
        "night_owl",
        night_owl,
        frozenset({"extend_notification_window:heartbeat"}),
        # Twenty notifications met with silence in a month is a fair question.
        defensible=frozenset({"review_notifications:heartbeat"}),
    ),
    Persona("silent", silent, frozenset({"review_notifications:heartbeat"})),
    Persona(
        "engaged",
        engaged,
        frozenset({"automate_need:event@daily"}),
        # Asking for the agenda around 7-8 h, before the notifications start at 9.
        defensible=frozenset({"extend_notification_window:heartbeat"}),
    ),
    Persona("sparse", sparse, frozenset()),
    Persona(
        "no_connector",
        no_connector,
        frozenset({"connect_source:email", "automate_need:event@daily"}),
    ),
    Persona(
        "weekly_planner",
        weekly_planner,
        frozenset({"automate_need:event@weekly", "automate_need:task@weekly"}),
    ),
    Persona("drifting", drifting, frozenset()),
    Persona(
        "bench",
        bench,
        frozenset(
            {
                "automate_need:event@daily",
                "automate_need:email@daily",
                "extend_notification_window:heartbeat",
                "review_notifications:heartbeat",
            }
        ),
        defensible=frozenset({"automate_need:weather@daily", "automate_need:email@weekdays"}),
    ),
)


# ---------------------------------------------------------------------------
# One night, read the way the nightly job reads it
# ---------------------------------------------------------------------------


def _in_window(day: date, today: date) -> bool:
    return today - timedelta(days=WINDOW_DAYS) < day <= today


def _routine_view(routine: Routine, today: date) -> RoutineView:
    return RoutineView(
        id=routine.id,
        title=routine.title,
        enabled=True,
        status="active",
        trigger_kind="time",
        times=(routine.hour,),
        fires_on=frozenset(range(7)),
        consecutive_failures=0,
        runs=tuple(run for run in routine.runs if _in_window(run.day, today)),
        read_domains=routine.reads,
        fixed_times=True,
    )


def _feedback(life: Life, today: date) -> ProactiveFeedback:
    window = [reacted for day, reacted in life.notifications if _in_window(day, today)]
    return ProactiveFeedback(sent=len(window), reacted=sum(window))


def observe(life: Life, today: date) -> UsageObservations:
    """The observations the nightly job would gather for this person tonight."""
    presence = {
        day: frozenset(hours)
        for day, hours in life.presence.items()
        if _in_window(day, today) and hours
    }
    ledger = LedgerView(readable=True, days_by_domain=life.asks, intents={})
    return UsageObservations(
        today=today,
        needs=needs_from_ledger(
            ledger, active_days=len(presence), today=today, thresholds=NEED_BARS
        ),
        need_status={},
        asked_days={
            domain: sum(1 for day in days if _in_window(day, today))
            for domain, days in life.asks.items()
        },
        routines=tuple(_routine_view(routine, today) for routine in life.routines),
        presence=presence,
        heartbeat_enabled=life.heartbeat,
        heartbeat_window=NOTIFY_WINDOW,
        proactive=_feedback(life, today),
        connector_categories=life.connectors,
        refusals={},
        ledger_readable=True,
    )


def identity(candidate: ProposalCandidate) -> str:
    """``kind:key``, and the cadence of an automation."""
    name = f"{candidate.kind.value}:{candidate.key}"
    if candidate.kind is ProposalKind.AUTOMATE_NEED:
        name += f"@{candidate.payload['cadence']}"
    return name


def simulate(persona: Persona, seed: int, nights: int) -> tuple[dict[str, int], frozenset[str]]:
    """Live the persona's month; return each proposal's first night and the last night's set."""
    rng = random.Random(f"{persona.name}:{seed}")
    life = Life()
    first: dict[str, int] = {}
    final: frozenset[str] = frozenset()
    for i in range(nights):
        day = START + timedelta(days=i)
        persona.live(life, rng, day, i)
        tonight = day + timedelta(days=1)  # the job runs in the small hours after the day
        final = frozenset(
            identity(c)
            for c in evaluate_proposals(observe(life, tonight), PROPOSAL_BARS).candidates
        )
        for name in final:
            first.setdefault(name, i + 1)
    return first, final


@dataclass(frozen=True, slots=True)
class PersonaReport:
    """One persona over every seed."""

    name: str
    seeds: int
    expected: dict[str, tuple[float, float | None]]  # rate on the last night, median first night
    defensible: dict[str, float]  # rate on the last night
    unexpected: dict[str, float]  # rate on the last night


def measure(personas: Sequence[Persona], seeds: int, nights: int) -> list[PersonaReport]:
    """Simulate every persona over ``seeds`` seeds of ``nights`` nights."""
    reports = []
    for persona in personas:
        hits: Counter[str] = Counter()
        firsts: dict[str, list[int]] = {name: [] for name in persona.expected}
        strays: Counter[str] = Counter()
        for seed in range(seeds):
            first, final = simulate(persona, seed, nights)
            for name in final & persona.expected:
                hits[name] += 1
                firsts[name].append(first[name])
            strays.update(final - persona.expected)
        defensible = {
            name: strays.pop(name) / seeds for name in sorted(persona.defensible & set(strays))
        }
        reports.append(
            PersonaReport(
                name=persona.name,
                seeds=seeds,
                expected={
                    name: (
                        hits[name] / seeds,
                        statistics.median(firsts[name]) if firsts[name] else None,
                    )
                    for name in sorted(persona.expected)
                },
                defensible=defensible,
                unexpected={name: count / seeds for name, count in strays.most_common()},
            )
        )
    return reports


def render(report: PersonaReport, nights: int) -> str:
    """The report of one persona, as printed."""
    lines = [f"\n== {report.name} ({report.seeds} seeds, {nights} nights)"]
    for name, (rate, median) in report.expected.items():
        lines.append(
            f"   expected   {name:<42} open on the last night {rate:>5.0%}   first night (median) {median}"
        )
    for name, rate in report.defensible.items():
        lines.append(f"   defensible {name:<42} open on the last night {rate:>5.0%}")
    for name, rate in report.unexpected.items():
        lines.append(f"   UNEXPECTED {name:<42} open on the last night {rate:>5.0%}")
    if not report.expected and not report.unexpected:
        lines.append("   nothing proposed, as expected")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--seeds", type=int, default=SEEDS)
    parser.add_argument("--nights", type=int, default=NIGHTS)
    parser.add_argument("--persona", action="append", help="Only this persona (repeatable).")
    args = parser.parse_args(argv)
    chosen = [p for p in PERSONAS if not args.persona or p.name in args.persona]
    if not chosen:
        parser.error(f"unknown persona; choose among {', '.join(p.name for p in PERSONAS)}")
    for report in measure(chosen, args.seeds, args.nights):
        print(render(report, args.nights))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
