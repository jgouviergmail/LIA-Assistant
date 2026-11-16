"""A judge reads whether an end-to-end answer STATES each expected fact (ADR-390).

The keyword oracle (``Case.oracle``) counts a fact as stated when its words appear
anywhere in the answer. Read by a person on 2026-11-15, it was wrong where words
mislead: « I could not find the day » above a five-day forecast naming it (E06),
« no reminder that day » above the very reminder of that day (E08), a word met only
in a suggestion (E14). A model now reads each fact the way that person did: stated
as true while answering — not denied, doubted, contradicted or only suggested.

The facts are written once per end-to-end case (:data:`FACTS`), aligned with the
keyword oracle, in technical English; ``{day+N}`` is the run's day plus N, with its
weekday. The judge is the instance's ``response`` slot, or the family named
(``--judge provider:model[@level]``): no model is written here, and it samples
greedily — at the slot's temperature it read one answer two ways. Its verdict is one
digit per fact; anything else is UNREADABLE — reported, never guessed.

What it cannot settle is said: an answer that gives the asked fact among others,
beside « I cannot find the day » (E06's forecast of the coming days), reads either
way — 0.67 on one replay, 0.00 on the next, for two near-identical answers. Two
clarified wordings were re-qualified on the hand-graded replay (2026-11-15) and
both did worse (118 and 116 facts of 120, against 120 for this one): the rule
stays, and every cell whose grade MOVED between replays is re-read by a person.

Run inside the API container, on a replay's turns (one JSON line per turn, with
``id``, ``draw``, ``mode`` and ``answer``), optionally against a person's grades::

    python -m scripts.agents.execution_mode_oracle --turns /tmp/e2e.jsonl \
        --day 2026-11-15 [--gold /tmp/gold.json] [--out /tmp/graded.jsonl]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Final

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage

from src.infrastructure.database.registry import import_all_models

# The bench opens a session (its slot's configuration, the tariffs): every mapper
# must be known before the first one is configured, as in the API's lifespan.
import_all_models()

from scripts.agents.execution_mode_corpus import E2E, Case  # noqa: E402
from scripts.llm_families import (  # noqa: E402
    family_llm,
    parse_families,
    prepare_bench,
    price_response,
)
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402

#: The slot a judge is asked through (the instance's own, unless a family is named).
JUDGE_SLOT: Final = "response"

#: One sentence per keyword fact of each end-to-end case, in the oracle's order.
FACTS: Final[dict[str, tuple[str, ...]]] = {
    "E01": (
        "a pending reminder to call the garage (garagiste) about the car's service",
        "a pending reminder to return the books to the library (médiathèque)",
        "a pending reminder to send the grant application (subvention) to the town hall",
        "a pending reminder to pay the sailing club fee (cotisation)",
    ),
    "E02": (
        "an open ticket about the kermesse budget",
        "an open ticket about booking the community hall (salle polyvalente)",
        "an open ticket about ordering the sailing team's t-shirts",
        "an open ticket about writing the general assembly minutes (compte rendu)",
        "an open ticket about finding a caterer (traiteur) for the school party",
    ),
    "E03": (
        "Hélène Garnier is the president (présidente)",
        "of the parents' association (association des parents d'élèves)",
    ),
    "E04": (
        "tomorrow's reminder is to call the garage (garagiste)",
        "a weather forecast for Nantes tomorrow",
        "a temperature for Nantes tomorrow",
    ),
    "E05": (
        "the urgent ticket is booking the community hall (salle polyvalente)",
        "a reminder within the next three days to call the garage",
        "a reminder within the next three days to return the library books",
        "a reminder within the next three days to send the grant application",
    ),
    "E06": (
        "the books must be returned to the library on {day+2}",
        "the weather in Nantes on {day+2}",
        "a temperature in Nantes on {day+2}",
    ),
    "E07": (
        "according to the ticket, Bastien Roux must give the t-shirt sizes",
        "Bastien Roux is the captain of the sailing team",
    ),
    "E08": (
        "the community hall ticket is due on {day+2}",
        "on that day there is a reminder: returning the books to the library",
    ),
    "E09": (
        "there are 2 tickets about the kermesse",
        "the first of their deadlines is in 2 days ({day+2})",
    ),
    "E10": ("the sailing club fee is due in 8 days ({day+8})",),
    "E11": (
        "there are 3 reminders in the next three days",
        "the first of them fires at 17:30",
    ),
    "E12": (
        "the community hall ticket is due this week",
        "the kermesse budget ticket is due this week",
        "none of the tickets due this week has a corresponding reminder",
    ),
    "E13": (
        "a ticket names Hélène Garnier",
        "Hélène Garnier is the president of the parents' association",
        "a ticket names Bastien Roux",
        "Bastien Roux is the captain of the sailing team",
    ),
    "E14": (
        "taking care of the car is the reminder to call the garage about its service",
        "it is due on {day+1}",
    ),
    "E15": (
        "a ticket about finding a caterer for the school party (fête de l'école)",
        "a ticket about writing the general assembly minutes (assemblée générale)",
    ),
    "E16": ("the person is allergic to peanuts (arachides)",),
    "E17": (
        "this week: the reminder to call the garage",
        "this week: booking the community hall",
        "this week: the kermesse budget ticket",
        "this week: the reminder to return the library books",
        "this week: the reminder to send the grant application",
    ),
    "E18": (
        "the plan includes preparing the kermesse budget",
        "the plan includes booking the community hall",
    ),
    "E19": (
        "booking the community hall is a priority",
        "the kermesse budget or finding a caterer is among the priorities",
    ),
    "E20": ("the weather in Bordeaux tomorrow", "a temperature for Bordeaux tomorrow"),
    "E21": (
        "tomorrow's weather in Lille",
        "tomorrow's weather in Marseille",
        "a temperature for tomorrow in Lille or Marseille",
    ),
    "E22": ("2,345 multiplied by 18 is 42,210",),
    "E24": ("photosynthesis uses light (sunlight)", "it is what plants do"),
}

_DAY_OFFSET = re.compile(r"\{day\+(\d+)\}")
#: Written out, not ``strftime``: the process's locale would name the day in its language.
_WEEKDAYS: Final = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

JUDGE_REQUEST: Final = """You check an assistant's answer against the facts it should state.

Request:
{request}

Answer:
<<<
{answer}
>>>

For each numbered fact, write 1 when the answer states it as true while answering the
request, 0 otherwise. A fact the answer denies, doubts, says it could not find or could
not check, contradicts itself about, or mentions only in a suggestion or a question, is
0. Other wording, another language or another date format still counts.

Facts:
{facts}

Reply with the digits only, one per fact, separated by spaces."""


def render(sentence: str, run_day: date) -> str:
    """A fact with ``{day+N}`` written as the run's day plus N and its weekday (pure)."""

    def _day(match: re.Match[str]) -> str:
        day = run_day + timedelta(days=int(match.group(1)))
        return f"{day.isoformat()} ({_WEEKDAYS[day.weekday()]})"

    return _DAY_OFFSET.sub(_day, sentence)


def judge_request(case: Case, answer: str, run_day: date) -> str:
    """What the judge reads for one answer (pure)."""
    facts = FACTS.get(case.case_id, ())
    numbered = "\n".join(
        f"{index}. {render(fact, run_day)}" for index, fact in enumerate(facts, start=1)
    )
    return JUDGE_REQUEST.format(request=case.text, answer=answer, facts=numbered)


def read_verdict(text: str, count: int) -> tuple[bool, ...] | None:
    """One boolean per fact, or None when the verdict is not exactly that (pure)."""
    digits = text.split()
    if len(digits) != count or any(digit not in ("0", "1") for digit in digits):
        return None
    return tuple(digit == "1" for digit in digits)


@dataclass(frozen=True)
class Graded:
    """One answer, read: a verdict per fact (None when unreadable) and its cost."""

    facts: tuple[bool, ...] | None
    cost_eur: float

    @property
    def score(self) -> float | None:
        """The share of facts stated, or None for an unreadable verdict."""
        if self.facts is None:
            return None
        return sum(self.facts) / len(self.facts) if self.facts else 1.0


async def grade(llm: BaseChatModel, model: str, case: Case, answer: str, run_day: date) -> Graded:
    """Ask the judge whether ``answer`` states each fact of ``case``.

    Args:
        llm: The judge.
        model: Its name, to price what it answered.
        case: The end-to-end case.
        answer: The assistant's answer, as the person read it.
        run_day: The replay's day in the account's timezone.

    Returns:
        The verdict and what it cost; a case with no fact needs no judge.
    """
    facts = FACTS.get(case.case_id, ())
    if not facts:
        return Graded(facts=(), cost_eur=0.0)
    response = await llm.ainvoke([HumanMessage(content=judge_request(case, answer, run_day))])
    verdict = read_verdict(coerce_content_to_text(response.content), len(facts))
    return Graded(facts=verdict, cost_eur=price_response(response, model).cost_eur)


def _turns(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if "answer" in row and "mode" in row]


def _answer(row: dict[str, object]) -> str:
    answer = row.get("answer")
    text = answer if isinstance(answer, str) else ""
    # A harness may have stored the answer JSON-encoded.
    return json.loads(text) if text.startswith('"') else text


def agreement(
    graded: dict[tuple[str, int, str], Graded], gold: dict[str, Sequence[int]]
) -> tuple[int, int, list[str]]:
    """How many facts the judge reads as the person did, out of how many, and where not.

    Args:
        graded: The judge's verdicts, by (case, draw, mode).
        gold: The person's grades, by ``"case/draw/mode"``, one 0/1 per fact.

    Returns:
        (agreeing facts, compared facts, the cells where they differ).
    """
    agree = compared = 0
    differing: list[str] = []
    for key, expected in gold.items():
        case_id, draw, mode = key.split("/")
        read = graded.get((case_id, int(draw), mode))
        if read is None or read.facts is None:
            differing.append(f"{key} unread")
            continue
        for index, (judged, person) in enumerate(zip(read.facts, expected, strict=True)):
            compared += 1
            if judged == bool(person):
                agree += 1
            else:
                differing.append(f"{key} fact {index + 1}: judge {int(judged)}, person {person}")
    return agree, compared, differing


Cell = tuple[str, int, str]


async def _grade_all(
    rows: Sequence[dict[str, object]], run_day: date, judge: str | None
) -> tuple[str, dict[Cell, Graded]]:
    """Every turn's answer, read by the judge — the bench's only waits."""
    await prepare_bench()
    by_id = {case.case_id: case for case in E2E}
    (family,) = parse_families(judge)
    model, llm, _config = family_llm(JUDGE_SLOT, family, temperature=0.0)
    graded: dict[Cell, Graded] = {}
    for row in rows:
        case = by_id.get(str(row.get("id")))
        if case is None:
            continue
        key = (case.case_id, int(str(row.get("draw", 0))), str(row["mode"]))
        graded[key] = await grade(llm, model, case, _answer(row), run_day)
    return model, graded


def _report(model: str, graded: dict[Cell, Graded], gold: dict[str, Sequence[int]] | None) -> None:
    """The completeness per engine, the unreadable verdicts and the agreement with a person."""
    means: dict[str, list[float]] = defaultdict(list)
    unreadable = 0
    for (_case_id, _draw, mode), read in graded.items():
        if read.score is None:
            unreadable += 1
        else:
            means[mode].append(read.score)
    for mode, scores in sorted(means.items()):
        print(f"{mode}: completeness {sum(scores) / len(scores):.3f} over {len(scores)} answers")
    print(
        f"unreadable verdicts: {unreadable}; judge: {model}; spend: "
        f"€{sum(read.cost_eur for read in graded.values()):.4f}"
    )
    if gold is not None:
        agree, compared, differing = agreement(graded, gold)
        print(f"agreement with the person: {agree}/{compared}")
        for line in differing:
            print(f"  {line}")


def _write(graded: dict[Cell, Graded], path: Path) -> None:
    with path.open("w", encoding="utf-8") as out:
        for (case_id, draw, mode), read in graded.items():
            facts = None if read.facts is None else [int(fact) for fact in read.facts]
            out.write(json.dumps({"id": case_id, "draw": draw, "mode": mode, "facts": facts}))
            out.write("\n")


def main(argv: list[str] | None = None) -> int:
    """Grade a replay's turns with the judge."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--turns", required=True, help="the replay's turns, one JSON line each")
    parser.add_argument("--day", required=True, help="the replay's day, YYYY-MM-DD")
    parser.add_argument("--judge", default=None, help="provider:model[@level]; the slot otherwise")
    parser.add_argument("--gold", default=None, help="a person's grades, to measure agreement")
    parser.add_argument("--out", default=None, help="write every verdict as one JSON line")
    args = parser.parse_args(argv)
    rows = _turns(Path(args.turns))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8")) if args.gold else None
    model, graded = asyncio.run(_grade_all(rows, date.fromisoformat(args.day), args.judge))
    _report(model, graded, gold)
    if args.out:
        _write(graded, Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
