"""Measure whether a model answers time-bound questions better when each message says WHEN.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money (lot 17).
Today the response model knows the present (``<TemporalContext>``: « Current date
and time ») but no earlier message carries the moment it was written: a history
restored days later reads as if everything had been said just now. « Is my dentist
appointment still ahead? » about « I have the dentist tomorrow », said three days
ago, has one right answer, and only the date of the message gives it.

Three arms, the same question, the same model:

- ``plain``: the history as production sends it — the messages, no time;
- ``stamped``: each earlier message prefixed with the wall time it was written in
  the person's zone, and ONE sentence in the system prompt saying what the stamps
  are;
- ``stamped_person``: only the PERSON's earlier messages stamped — production's
  variant, where a turn begins with the person and LIA's answer follows at once —
  and the sentence saying that some earlier messages carry one.

The corpus is written for its fixed present (``NOW``, a Friday): « due on Friday »
said nine days earlier means a Friday already gone. Time-bound questions expect
both answers, so a model always answering « no » cannot win; the CONTROLS ask what
was said, not when, so a stamp that confuses a model shows there. Each question
asks for a verdict first (« YES/NO », or a number), which is what is read. The
system prompt is reduced to the present and the stamps: a capability probe, not
the full response prompt — a cut stated, not hidden.

``--models`` names the families (``provider:model[@level]``); without it the
instance's own response slot is asked. Run inside the API container::

    python -m scripts.agents.measure_message_timestamps --dry-run
    python -m scripts.agents.measure_message_timestamps --models deepseek:deepseek-flash
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final, Literal
from zoneinfo import ZoneInfo

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from scripts.llm_families import (  # noqa: E402
    Family,
    family_llm,
    parse_families,
    prepare_bench,
    price_response,
)
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402

RESPONSE_SLOT: Final = "response"
#: The present the corpus is written for: Friday 13 November 2026, 09:30 UTC.
NOW: Final = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)
#: The arms, in the order asked: no time, every earlier message stamped, only the
#: person's messages (a turn begins with the person, and LIA's answer follows at
#: once), and production's rule — the person's messages, the current question too.
ARMS: Final = ("plain", "stamped", "stamped_person", "stamped_person_now")
#: The one sentence the stamped arm adds to the system prompt.
STAMP_SENTENCE: Final = (
    "Each earlier message starts with the date and time it was written, in "
    "brackets; the user's current message has none."
)
#: What the person arm says instead: SOME earlier messages carry a stamp.
PERSON_STAMP_SENTENCE: Final = (
    "An earlier message may start with the date and time it was written, in "
    "brackets; the user's current message has none."
)
#: What production says: a message (the question too) may carry one.
PRODUCTION_STAMP_SENTENCE: Final = (
    "A message may start with the date and time it was written, in brackets."
)
#: How much of an answer the report keeps.
EXCERPT_CHARS: Final = 160
_VERDICT = re.compile(r"\b(yes|no)\b|\b(\d+)\b", re.IGNORECASE)

#: Which earlier messages an arm stamps: none, all, or the person's.
Stamping = bool | Literal["person"]
_STAMPING: Final[dict[str, Stamping]] = {
    "plain": False,
    "stamped": True,
    "stamped_person": "person",
    "stamped_person_now": "person",
}
#: The arms whose current question carries the present too (production's rule:
#: its bytes are then the same once it is earlier).
_QUESTION_STAMPED: Final = frozenset({"stamped_person_now"})


@dataclass(frozen=True)
class Said:
    """One earlier message: who wrote it, what, and how long before the question."""

    role: Literal["person", "assistant"]
    text: str
    ago: timedelta


@dataclass(frozen=True)
class Scenario:
    """A history, the current question, and its one right verdict."""

    key: str
    history: tuple[Said, ...]
    question: str
    #: ``YES``, ``NO`` or a number written in digits.
    expected: str
    #: True when only WHEN things were said gives the answer; False for a control.
    time_bound: bool


_YES_NO = " Start your answer with YES or NO."
_NUMBER = " Start your answer with the number, in digits."

CORPUS: Final[tuple[Scenario, ...]] = (
    Scenario(
        "dentist_passed",
        (
            Said("person", "I have the dentist tomorrow at 10.", timedelta(days=3)),
            Said("assistant", "Noted, good luck at the dentist tomorrow.", timedelta(days=3)),
        ),
        "Is my dentist appointment still ahead of me?" + _YES_NO,
        "NO",
        True,
    ),
    Scenario(
        "dentist_ahead",
        (
            Said("person", "I have the dentist tomorrow at 10.", timedelta(hours=2)),
            Said("assistant", "Noted, good luck at the dentist tomorrow.", timedelta(hours=2)),
        ),
        "Is my dentist appointment still ahead of me?" + _YES_NO,
        "YES",
        True,
    ),
    Scenario(
        "flight_gone",
        (Said("person", "My flight leaves in two hours, I'm at the gate.", timedelta(days=2)),),
        "Am I still waiting for that flight to leave?" + _YES_NO,
        "NO",
        True,
    ),
    Scenario(
        "report_friday_gone",
        (
            Said("person", "The quarterly report is due on Friday.", timedelta(days=9)),
            Said("assistant", "Understood, I'll keep that in mind.", timedelta(days=9)),
        ),
        "Is the quarterly report I mentioned due today?" + _YES_NO,
        "NO",
        True,
    ),
    Scenario(
        "package_due",
        (Said("person", "My package should arrive in two days.", timedelta(days=3)),),
        "Should my package have arrived by now?" + _YES_NO,
        "YES",
        True,
    ),
    Scenario(
        "call_evening_gone",
        (Said("person", "I need to call Paul tonight.", timedelta(days=1, hours=2)),),
        "Has the evening I meant for calling Paul already gone by?" + _YES_NO,
        "YES",
        True,
    ),
    Scenario(
        "back_pain_days",
        (
            Said("person", "My back has been hurting since this morning.", timedelta(days=4)),
            Said("assistant", "Sorry to hear that. Rest helps.", timedelta(days=4)),
            Said("person", "Still hurting a bit.", timedelta(days=1)),
        ),
        "How many days ago did I first tell you about my back?" + _NUMBER,
        "4",
        True,
    ),
    Scenario(
        "sister_city",
        (Said("person", "My sister lives in Lyon.", timedelta(days=2)),),
        "Did I tell you my sister lives in Lyon?" + _YES_NO,
        "YES",
        False,
    ),
    Scenario(
        "peanut_allergy",
        (Said("person", "I'm allergic to peanuts.", timedelta(days=10)),),
        "Am I allergic to peanuts?" + _YES_NO,
        "YES",
        False,
    ),
    Scenario(
        "no_pets",
        (Said("person", "I don't have any pets.", timedelta(days=1)),),
        "Do I have a cat?" + _YES_NO,
        "NO",
        False,
    ),
    Scenario(
        "children_count",
        (Said("person", "I have three children.", timedelta(days=6)),),
        "How many children do I have?" + _NUMBER,
        "3",
        False,
    ),
)


@dataclass
class Outcome:
    """One question asked of one family in one arm, and what it answered."""

    model: str
    arm: str
    scenario: str
    verdict: str | None
    expected: str
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cost_eur: float = 0.0
    seconds: float = 0.0
    answer: str = ""

    @property
    def correct(self) -> bool:
        return self.error is None and self.verdict == self.expected


def _wall(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%a %d %b %Y, %H:%M")


def stamp(text: str, sent_at: datetime, zone: ZoneInfo) -> str:
    """A message prefixed with the wall time it was written in the person's zone."""
    return f"[{_wall(sent_at, zone)}] {text}"


def history_messages(
    scenario: Scenario, *, now: datetime, zone: ZoneInfo, stamped: Stamping
) -> list[BaseMessage]:
    """The earlier messages as the model receives them in one arm."""
    messages: list[BaseMessage] = []
    for said in scenario.history:
        carries = stamped is True or (stamped == "person" and said.role == "person")
        text = stamp(said.text, now - said.ago, zone) if carries else said.text
        messages.append(HumanMessage(text) if said.role == "person" else AIMessage(text))
    return messages


def current_question(
    scenario: Scenario, *, now: datetime, zone: ZoneInfo, arm: str
) -> HumanMessage:
    """The question as the model receives it: stamped with the present in production's arm."""
    if arm in _QUESTION_STAMPED:
        return HumanMessage(stamp(scenario.question, now, zone))
    return HumanMessage(scenario.question)


def system_prompt(
    now: datetime, zone: ZoneInfo, *, stamped: Stamping, question_stamped: bool = False
) -> str:
    """The present, as production's ``<TemporalContext>`` gives it, and the stamps' meaning."""
    lines = [
        "You are LIA, the user's personal assistant. Answer the user's current message.",
        f"<TemporalContext>Current date and time: {_wall(now, zone)}</TemporalContext>",
    ]
    if question_stamped:
        lines.append(PRODUCTION_STAMP_SENTENCE)
    elif stamped == "person":
        lines.append(PERSON_STAMP_SENTENCE)
    elif stamped:
        lines.append(STAMP_SENTENCE)
    return "\n".join(lines)


def verdict(answer: str) -> str | None:
    """The first verdict an answer gives: ``YES``, ``NO`` or a number; None when none."""
    match = _VERDICT.search(answer)
    if match is None:
        return None
    return match.group(1).upper() if match.group(1) else match.group(2)


def tally(rows: list[Outcome]) -> dict[tuple[str, str], dict[str, tuple[int, int]]]:
    """Correct and asked, per family and arm, time-bound questions apart from controls."""
    timed = {scenario.key: scenario.time_bound for scenario in CORPUS}
    counts: dict[tuple[str, str], Counter[str]] = {}
    for row in rows:
        bucket = counts.setdefault((row.model, row.arm), Counter())
        kind = "time_bound" if timed[row.scenario] else "controls"
        bucket[f"{kind}_asked"] += 1
        bucket[f"{kind}_correct"] += int(row.correct)
    return {
        key: {
            kind: (bucket[f"{kind}_correct"], bucket[f"{kind}_asked"])
            for kind in ("time_bound", "controls")
        }
        for key, bucket in counts.items()
    }


async def ask(
    scenario: Scenario,
    arm: str,
    model: str,
    llm: BaseChatModel,
    zone: ZoneInfo,
) -> Outcome:
    """Ask one family one question in one arm."""
    stamped = _STAMPING[arm]
    messages = [
        SystemMessage(
            system_prompt(NOW, zone, stamped=stamped, question_stamped=arm in _QUESTION_STAMPED)
        ),
        *history_messages(scenario, now=NOW, zone=zone, stamped=stamped),
        current_question(scenario, now=NOW, zone=zone, arm=arm),
    ]
    row = Outcome(model, arm, scenario.key, None, scenario.expected)
    started = time.perf_counter()
    try:
        response = await llm.ainvoke(messages)
    except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
        row.error = f"{type(exc).__name__}: {str(exc)[:200]}"
        row.seconds = round(time.perf_counter() - started, 1)
        return row
    row.seconds = round(time.perf_counter() - started, 1)
    text = coerce_content_to_text(response.content)
    row.verdict = verdict(text)
    row.answer = text.strip()[:EXCERPT_CHARS]
    priced = price_response(response, model)
    row.tokens_in, row.tokens_out = priced.tokens_in, priced.tokens_out
    row.cost_usd, row.cost_eur = priced.cost_usd, priced.cost_eur
    return row


def _summary(rows: list[Outcome]) -> str:
    lines = [
        "| model | arm | time-bound correct | controls correct |",
        "|---|---|---|---|",
    ]
    for (model, arm), kinds in sorted(tally(rows).items()):
        timed, controls = kinds["time_bound"], kinds["controls"]
        lines.append(f"| {model} | {arm} | {timed[0]}/{timed[1]} | {controls[0]}/{controls[1]} |")
    wrong = [row for row in rows if not row.correct]
    if wrong:
        lines += [
            "",
            "| model | arm | scenario | expected | read | answer |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {row.model} | {row.arm} | {row.scenario} | {row.expected} | {row.verdict} "
            f"| {(row.error or row.answer).replace('|', '/')} |"
            for row in wrong
        ]
    return "\n".join(lines)


def chosen_arms(spec: str | None) -> tuple[str, ...]:
    """The arms a run asks: all of them, or the ones named.

    Raises:
        SystemExit: An arm the bench does not know.
    """
    if not spec:
        return ARMS
    named = tuple(arm.strip() for arm in spec.split(",") if arm.strip())
    unknown = [arm for arm in named if arm not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arms: {', '.join(unknown)} (known: {', '.join(ARMS)})")
    return named


async def _measure(
    families: list[Family | None],
    zone: ZoneInfo,
    reps: int,
    budget_eur: float,
    arms: tuple[str, ...] = ARMS,
) -> list[Outcome]:
    """Ask every family every question in both arms, until the budget is reached."""
    await prepare_bench()
    rows: list[Outcome] = []
    spent = 0.0
    for family in families:
        model, llm, _config = family_llm(RESPONSE_SLOT, family)
        for scenario in CORPUS:
            for arm in arms:
                for _ in range(reps):
                    if spent > budget_eur:  # every remaining question is skipped, none is cut
                        break
                    row = await ask(scenario, arm, model, llm, zone)
                    rows.append(row)
                    spent += row.cost_eur
                    print(json.dumps(asdict(row), ensure_ascii=False), flush=True)
    if spent > budget_eur:
        print(f"stopped: {budget_eur} EUR reached", file=sys.stderr)
    return rows


async def _amain(args: argparse.Namespace) -> int:
    zone = ZoneInfo(args.zone)
    if args.dry_run:
        for scenario in CORPUS:
            for arm in chosen_arms(args.arms):
                stamped = _STAMPING[arm]
                print(f"--- {scenario.key} [{arm}] expects {scenario.expected}")
                print(
                    system_prompt(
                        NOW, zone, stamped=stamped, question_stamped=arm in _QUESTION_STAMPED
                    )
                )
                for message in history_messages(scenario, now=NOW, zone=zone, stamped=stamped):
                    print(f"{message.type}: {message.content}")
                print(f"human: {current_question(scenario, now=NOW, zone=zone, arm=arm).content}")
        return 0
    started = time.perf_counter()
    rows = await _measure(
        parse_families(args.models), zone, args.reps, args.budget_eur, chosen_arms(args.arms)
    )
    report = {
        "tally": {f"{model}|{arm}": kinds for (model, arm), kinds in tally(rows).items()},
        "cost_eur": round(sum(row.cost_eur for row in rows), 4),
        "cost_usd": round(sum(row.cost_usd for row in rows), 4),
        "seconds": round(time.perf_counter() - started, 1),
        "rows": [asdict(row) for row in rows],
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(rows))
    print(json.dumps({key: value for key, value in report.items() if key != "rows"}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        help="provider:model[@level],... (default: the instance's own response slot)",
    )
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--arms", help=f"Comma-separated arms (default: {','.join(ARMS)})")
    parser.add_argument(
        "--zone", default=DEFAULT_USER_DISPLAY_TIMEZONE, help="The person's zone (IANA)"
    )
    parser.add_argument("--budget-eur", type=float, default=0.30, help="Stop past this spend (EUR)")
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="Print what is asked, ask nothing")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
