"""Measure the automatic mode's shape judgement on its held-out corpus (ADR-390).

A MEASUREMENT, never a gate: it asks the instance's decision provider and spends
money, on the PROOF account alone (``scripts/proof_account.py``). Every case of
``scripts/agents/execution_mode_corpus.py`` is asked through the production door
(``choose_many_with_jev``, usage ``execution_mode``, the versioned questions) and
read by the production verdict (``shape_verdict``, at the margins the operation
froze): a margin moved in the administration is measured exactly as it decides.

It judges the JUDGEMENT alone, on what it answers for: a LEAK is a case labelled
with one of the properties it is asked about (``PROPERTIES``: a computed figure, a
cross-check, open-ended work, someone or something only an item's text names) and
judged plannable. A case that needs the loop for a reason no property states — an
act, item-by-item work, a follow-up — is the router's analysis's to catch, before
any judgement; it is listed apart (« left to the analysis »), never counted for or
against the judgement. The corpus's declared acceptance is then read on the leaks,
split by split, with what a property declared beyond it (``PROPERTY_ACCEPTANCE``).

A margin is chosen on calibration from what separates a property's labelled cases
from the plannable ones — the lowest labelled score, the highest plannable one,
both reported — and ``--rows-out`` keeps every judgement as one line of facts.

Through the production door, its judgements also count in the usage's durable
statistics (ADR-374) like any turn's, and its spend is the proof account's: run it
on dev.

Read first the leaks, then the lane (the plannable cases the pipeline may take),
then the cases judged differently between draws. Run inside the API container,
which holds the configuration and the tariffs::

    python -m scripts.agents.measure_execution_mode --dry-run
    python -m scripts.agents.measure_execution_mode --draws 2 --budget-eur 0.10
    python -m scripts.agents.measure_execution_mode --split calibration --rows-out /tmp/rows.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Final

from src.infrastructure.database.registry import import_all_models

import_all_models()

from scripts.agents.execution_mode_corpus import (  # noqa: E402
    CASES,
    PROPERTIES,
    PROPERTY_ACCEPTANCE,
    Case,
    PropertyAcceptance,
)
from scripts.proof_account import proof_user  # noqa: E402
from src.domains.agents.services.analysis.jev_execution_mode import (  # noqa: E402
    property_absent,
    shape_questions,
    shape_verdict,
)
from src.domains.agents.services.engine_resolution import EngineReason  # noqa: E402
from src.domains.llm_config.jev_registry import JevUsage  # noqa: E402
from src.domains.llm_config.jev_settings import (  # noqa: E402
    JevSnapshot,
    read_configuration,
    read_routing,
    resolve_thresholds,
)
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.decision_types import DecisionAttempt  # noqa: E402
from src.infrastructure.llm.jev_runtime import choose_many_with_jev  # noqa: E402

DEFAULT_DRAWS: Final = 2
DEFAULT_BUDGET_EUR: Final = 0.10
#: At most this many leaks on validation — the corpus's declared bound.
MAX_VALIDATION_LEAKS: Final = 1

Ask = Callable[[str], Awaitable[DecisionAttempt]]


@dataclass(frozen=True, slots=True)
class Judgement:
    """What one draw of one case was judged — facts only, never the request."""

    case_id: str
    draw: int
    outcome: str
    nouls: dict[str, float]
    verdict: EngineReason
    cost_eur: float
    duration_ms: float


@dataclass
class PropertyCount:
    """What one property's cases did on one split.

    Attributes:
        leaks: Draws of a case labelled with it, judged plannable.
        absent: Draws of its declared hard negatives on which IT was judged absent.
        lane: Draws of its declared hard negatives judged plannable (every question).
        negatives: Draws of its declared hard negatives.
    """

    leaks: int = 0
    absent: int = 0
    lane: int = 0
    negatives: int = 0


@dataclass
class SplitReport:
    """One split, as the corpus's acceptance reads it.

    Attributes:
        lane: Plannable draws judged plannable (``direct``).
        plannable: Plannable draws (neither needs-loop nor ambiguous).
        leaks: Draws of a case labelled with a judged property, judged plannable:
            (case, shape, draw).
        left_to_analysis: Draws of a needs-loop case no property labels (an act,
            item-by-item work, a follow-up), judged plannable: the analysis's.
        unstable: Cases whose verdict differs between draws.
        undecided: Draws with no usable judgement.
        properties: Each property's own counts.
        separation: Each property's lowest score on a draw of a case labelled with
            it and highest on a plannable draw; None where no such draw answered.
    """

    lane: int = 0
    plannable: int = 0
    leaks: list[tuple[str, str, int]] = field(default_factory=list)
    left_to_analysis: list[tuple[str, str, int]] = field(default_factory=list)
    unstable: list[str] = field(default_factory=list)
    undecided: int = 0
    properties: dict[str, PropertyCount] = field(default_factory=dict)
    separation: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)


def read_judgement(attempt: DecisionAttempt) -> tuple[dict[str, float], EngineReason]:
    """The answers an attempt carries, and the production verdict on them."""
    nouls = {key: answer.noul for key, answer in attempt.nouls.items()}
    return nouls, shape_verdict(attempt)


async def run(cases: Sequence[Case], *, draws: int, ask: Ask, budget_eur: float) -> list[Judgement]:
    """Ask every case once per draw, stopping as soon as the budget is spent.

    Args:
        cases: The corpus cases to ask.
        draws: How many times each case is asked.
        ask: The decision door, given the request's words.
        budget_eur: The spend after which no further call leaves.

    Returns:
        One judgement per call made, in the order they were made.
    """
    rows: list[Judgement] = []
    spent = 0.0
    for draw in range(draws):
        for case in cases:
            if spent >= budget_eur:
                return rows
            started = perf_counter()
            attempt = await ask(case.text)
            # What the router waits for: the whole door, quota gate and accounting included.
            duration = (perf_counter() - started) * 1000
            nouls, verdict = read_judgement(attempt)
            cost = attempt.charge.cost_eur if attempt.charge else 0.0
            spent += cost
            rows.append(
                Judgement(case.case_id, draw, attempt.outcome, nouls, verdict, cost, duration)
            )
    return rows


#: Scores collected per (split, property).
_Scores = dict[tuple[str, str], list[float]]


def _count_draw(
    report: SplitReport,
    case: Case,
    row: Judgement,
    acceptance: Mapping[str, PropertyAcceptance],
    thresholds: Mapping[str, Decimal],
) -> None:
    """Count one draw of a non-ambiguous case where the acceptance reads it."""
    plannable = row.verdict is EngineReason.DIRECT
    for name, declared in acceptance.items():
        if case.case_id in declared.hard_negatives:
            count = report.properties.setdefault(name, PropertyCount())
            score = row.nouls.get(name)
            count.negatives += 1
            count.absent += score is not None and property_absent(thresholds, name, score)
            count.lane += plannable
    if not (case.judged() or case.needs_loop):
        report.plannable += 1
        report.lane += plannable
        return
    if not plannable:
        return
    missed = report.leaks if case.judged() else report.left_to_analysis
    missed.append((case.case_id, case.shape, row.draw))
    for name in PROPERTIES:
        if getattr(case, name):
            report.properties.setdefault(name, PropertyCount()).leaks += 1


def _collect_scores(case: Case, row: Judgement, labelled: _Scores, plannable: _Scores) -> None:
    """File each answered score of a non-ambiguous draw as labelled or plannable."""
    for name in PROPERTIES:
        score = row.nouls.get(name)
        if score is None:
            continue
        if getattr(case, name):
            labelled[(case.split, name)].append(score)
        elif not case.needs_loop:
            plannable[(case.split, name)].append(score)


def summarize(
    rows: Sequence[Judgement],
    cases: Sequence[Case],
    *,
    acceptance: Mapping[str, PropertyAcceptance] = PROPERTY_ACCEPTANCE,
    thresholds: Mapping[str, Decimal] | None = None,
) -> dict[str, SplitReport]:
    """Count the judgements split by split, as the corpus declares its acceptance.

    Args:
        rows: The judgements.
        cases: The corpus cases they answer.
        acceptance: What each property declared beyond the general bound.
        thresholds: The margins the run froze, for « judged absent » (defaults
            when None).

    Returns:
        One report per split.
    """
    margins: Mapping[str, Decimal] = thresholds or {}
    by_id = {case.case_id: case for case in cases}
    reports: dict[str, SplitReport] = defaultdict(SplitReport)
    verdicts: dict[str, set[EngineReason]] = defaultdict(set)
    labelled: _Scores = defaultdict(list)
    plannable: _Scores = defaultdict(list)
    for row in rows:
        case = by_id[row.case_id]
        report = reports[case.split]
        verdicts[row.case_id].add(row.verdict)
        if row.verdict is EngineReason.NO_DECISION:
            report.undecided += 1
        if case.ambiguous:
            continue
        _count_draw(report, case, row, acceptance, margins)
        _collect_scores(case, row, labelled, plannable)
    for case_id, seen in verdicts.items():
        if len(seen) > 1:
            reports[by_id[case_id].split].unstable.append(case_id)
    for split, report in reports.items():
        report.separation = {
            name: (
                min(labelled[(split, name)], default=None),
                max(plannable[(split, name)], default=None),
            )
            for name in PROPERTIES
        }
    return dict(reports)


def _property_failures(
    validation: SplitReport, acceptance: Mapping[str, PropertyAcceptance]
) -> list[str]:
    """What a property declared beyond the general bound, and this run fails."""
    failures: list[str] = []
    for name, declared in acceptance.items():
        count = validation.properties.get(name, PropertyCount())
        if count.leaks > declared.max_leaks:
            failures.append(
                f"validation: {count.leaks} draw(s) labelled {name} judged plannable "
                f"(at most {declared.max_leaks})"
            )
        if count.negatives and Fraction(count.absent, count.negatives) < declared.min_absent_share:
            failures.append(
                f"validation: {name} judged absent on {count.absent}/{count.negatives} draws "
                f"of its hard negatives (at least {declared.min_absent_share})"
            )
    return failures


def failed_criteria(
    reports: dict[str, SplitReport],
    *,
    acceptance: Mapping[str, PropertyAcceptance] = PROPERTY_ACCEPTANCE,
) -> list[str]:
    """The corpus's declared acceptance criteria this measurement fails, in words."""
    failures: list[str] = []
    validation = reports.get("validation")
    if validation is not None:
        if len(validation.leaks) > MAX_VALIDATION_LEAKS:
            failures.append(
                f"validation: {len(validation.leaks)} needs-loop cases judged plannable "
                f"(at most {MAX_VALIDATION_LEAKS})"
            )
        shapes = [shape for _case, shape, _draw in validation.leaks]
        failures.extend(
            f"validation: two leaks of shape {shape}"
            for shape in sorted(set(shapes))
            if shapes.count(shape) > 1
        )
        if validation.plannable and validation.lane * 2 < validation.plannable:
            failures.append(
                f"validation: {validation.lane}/{validation.plannable} plannable cases judged "
                "plannable (at least half)"
            )
        failures.extend(_property_failures(validation, acceptance))
    adversarial = reports.get("adversarial")
    if adversarial is not None:
        failures.extend(
            f"adversarial: an instruction moved {case_id} to the pipeline"
            for case_id, _shape, _draw in adversarial.leaks
        )
    return failures


async def qualification_snapshot() -> tuple[JevSnapshot, bool]:
    """The usage's routing as a turn reads it, whether its switch is on or not.

    A qualification precedes activation: the switch decides whether turns ask, never
    whether the margins can be measured. The slot's configuration and the stored
    margins are read exactly as an operation of the usage reads them.

    Returns:
        The snapshot to ask through, and whether the usage is switched on.
    """
    usage = JevUsage.EXECUTION_MODE
    async with get_db_context() as db:
        routing = await read_routing(db)
        thresholds = resolve_thresholds(usage, routing.thresholds.get(usage.value))
        readiness, configuration = await read_configuration(db, usage)
    switched_on = routing.flags["global"] and routing.flags[usage.value]
    return JevSnapshot(True, readiness, configuration, thresholds), switched_on


def write_rows(rows: Sequence[Judgement], path: Path) -> None:
    """Keep every judgement as one JSON line of facts — never a request's words.

    Args:
        rows: The judgements, as the run made them.
        path: Where to write them (replaced).
    """
    with path.open("w", encoding="utf-8") as out:
        for row in rows:
            fact = {
                "case_id": row.case_id,
                "draw": row.draw,
                "outcome": row.outcome,
                "nouls": row.nouls,
                "verdict": row.verdict.value,
                "cost_eur": row.cost_eur,
                "duration_ms": row.duration_ms,
            }
            out.write(json.dumps(fact) + "\n")


def _score(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _print_properties(report: SplitReport) -> None:
    """Each property's separation and own counts, as a margin is chosen from them."""
    for name in PROPERTIES:
        lowest, highest = report.separation.get(name, (None, None))
        count = report.properties.get(name, PropertyCount())
        negatives = (
            f"; hard negatives: judged absent {count.absent}/{count.negatives}, "
            f"in the lane {count.lane}/{count.negatives}"
            if count.negatives
            else ""
        )
        print(
            f"  {name}: labelled >= {_score(lowest)}, plannable <= {_score(highest)}; "
            f"leaks {count.leaks}{negatives}"
        )


def _print_report(rows: Sequence[Judgement], reports: dict[str, SplitReport]) -> None:
    """The report a person reads: leaks first, then the lane, then the unstable."""
    for split, report in sorted(reports.items()):
        print(f"== {split}")
        print(f"  leaks (a judged property, judged plannable): {report.leaks or 'none'}")
        print(f"  left to the analysis: {report.left_to_analysis or 'none'}")
        print(f"  lane: {report.lane}/{report.plannable} plannable draws judged plannable")
        print(f"  unstable between draws: {report.unstable or 'none'}")
        print(f"  undecided draws: {report.undecided}")
        _print_properties(report)
    durations = sorted(row.duration_ms for row in rows if row.duration_ms)
    if durations:
        p90 = durations[int(0.9 * (len(durations) - 1))]
        print(f"decision latency: median {statistics.median(durations):.0f} ms, p90 {p90:.0f} ms")
    outcomes: dict[str, int] = defaultdict(int)
    for row in rows:
        outcomes[row.outcome] += 1
    print(f"outcomes: {dict(outcomes)}")
    print(f"spend: €{sum(row.cost_eur for row in rows):.4f} over {len(rows)} calls")
    failures = failed_criteria(reports)
    print("acceptance: " + ("passed" if not failures else "FAILED — " + "; ".join(failures)))


async def _measure(args: argparse.Namespace) -> int:
    snapshot, switched_on = await qualification_snapshot()
    cases = [case for case in CASES if args.split in ("all", case.split)]
    margins = {key: str(value) for key, value in snapshot.thresholds.items()}
    print(
        f"slot readiness: {snapshot.readiness}; usage switched "
        f"{'on' if switched_on else 'off (measured anyway)'}; margins: {margins}"
    )
    print(f"{len(cases)} cases × {args.draws} draws, budget €{args.budget_eur:.2f}")
    if args.dry_run:
        for case in cases:
            print(f"  {case.case_id} {case.split} {case.shape} {case.lang} loop={case.needs_loop}")
        return 0
    if snapshot.configuration is None:
        print(f"the slot is not usable ({snapshot.readiness}): nothing to measure")
        return 1
    async with get_db_context() as db:
        user_id = (await proof_user(db)).id
    run_id = f"execution-mode-bench-{uuid.uuid4()}"

    async def ask(request: str) -> DecisionAttempt:
        return await choose_many_with_jev(
            usage=JevUsage.EXECUTION_MODE,
            user_id=user_id,
            run_id=run_id,
            state={"request": request},
            questions=shape_questions(),
            snapshot=snapshot,
        )

    rows = await run(cases, draws=args.draws, ask=ask, budget_eur=args.budget_eur)
    _print_report(rows, summarize(rows, cases, thresholds=snapshot.thresholds))
    if args.rows_out:
        write_rows(rows, Path(args.rows_out))
        print(f"rows: {len(rows)} judgements written to {args.rows_out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Parse the arguments and run the measurement."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    parser.add_argument("--budget-eur", type=float, default=DEFAULT_BUDGET_EUR)
    parser.add_argument(
        "--split", choices=("all", "calibration", "validation", "adversarial"), default="all"
    )
    parser.add_argument("--dry-run", action="store_true", help="list the cases, ask nothing")
    parser.add_argument(
        "--rows-out", help="also write every judgement as one JSON line of facts, for calibration"
    )
    return asyncio.run(_measure(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
