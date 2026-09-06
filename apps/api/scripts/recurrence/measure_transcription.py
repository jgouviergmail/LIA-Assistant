"""How well a model turns a spoken schedule into parameters — measured, not assumed.

The deterministic half (parameters to instants) is a unit test and runs in CI.
This is the other half, and it needs a provider key: this repository's CI holds
none, and a test that silently skips is decoration, not coverage
(ADR-155). So it is a SCRIPT — the shape `mobile:probe` and
`llm:catalogue:fetch` already use: run it on purpose, read the report, publish
the number with its date and its model.

    task recurrence:corpus:measure -- --slot planner --languages fr,en

**The oracle is the INSTANTS, not the parameters.** Two different parameter
sets that fire at the same moments are the same schedule, and a model that
says `repeat=weekly, weekdays=[1,2,3,4,5]` where the corpus says
`repeat=daily` on weekdays is not wrong. Comparing fields would report a
failure for a right answer — the mistake ADR-182 names.

Nothing here writes to the database, and nothing reads a user's data: the
corpus is a fixture, and the only network call is to the configured provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.core.recurrence import (  # noqa: E402
    RecurrenceError,
    occurrences,
    recurrence_from_parameters,
)
from src.domains.agents.registry.recurrence_parameters import RECURRENCE_DOCS  # noqa: E402

CORPUS_PATH = REPO_ROOT / "tests" / "unit" / "core" / "recurrence" / "transcription_corpus.json"

#: What the model is asked to produce. The DESCRIPTIONS are the ones the tool
#: publishes, so the measurement exercises the wording that actually ships —
#: measuring a prompt nobody uses would answer a question nobody asked.
_INSTRUCTIONS = """You turn a spoken schedule into parameters.

It is currently {now} on {today} ({weekday}), timezone {timezone}.
A time of day that has already passed today belongs to the next day.

Answer with a JSON object holding ONLY these keys, omitting the ones that do
not apply. No prose, no code fence.

{vocabulary}

The sentence to transcribe is between the markers.
<<<{utterance}>>>"""


def _vocabulary() -> str:
    return "\n".join(f"- {name}: {doc}" for name, doc in RECURRENCE_DOCS.items())


def _expected_instants(family: dict[str, Any], corpus: dict[str, Any]) -> list[str]:
    return family["expect"]


def _instants_of(
    params: dict[str, Any], family: dict[str, Any], corpus: dict[str, Any]
) -> list[str]:
    """The wall clocks a parameter set fires at, or an empty list if it cannot.

    Args:
        params: What the model produced.
        family: The corpus family it was answering.
        corpus: The corpus, for its reference instant.

    Returns:
        Local wall clocks, `YYYY-MM-DD HH:MM`, as many as the family expects.
    """
    zone = family.get("timezone", corpus["default_timezone"])
    reference = datetime.fromisoformat(family.get("expect_from", corpus["reference_now"]))
    today = reference.astimezone(ZoneInfo(zone)).date()
    try:
        spec = recurrence_from_parameters(**params, today=today)
    except RecurrenceError, TypeError, ValueError:
        return []
    fired = occurrences(spec, zone, after=reference, count=len(family["expect"]))
    return [i.astimezone(ZoneInfo(zone)).strftime("%Y-%m-%d %H:%M") for i in fired]


async def _ask(llm: Any, family: dict[str, Any], language: str, corpus: dict[str, Any]) -> dict:
    zone = family.get("timezone", corpus["default_timezone"])
    reference = datetime.fromisoformat(family.get("expect_from", corpus["reference_now"]))
    today = reference.astimezone(ZoneInfo(zone)).date()
    prompt = _INSTRUCTIONS.format(
        now=reference.astimezone(ZoneInfo(zone)).strftime("%H:%M"),
        today=today.isoformat(),
        weekday=today.strftime("%A"),
        timezone=zone,
        vocabulary=_vocabulary(),
        utterance=family["utterances"][language],
    )
    answer = await llm.ainvoke(prompt)
    text = getattr(answer, "text", None) or str(answer.content)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(text)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", default="planner", help="LLM slot to measure (default: planner)")
    parser.add_argument("--provider", default=None, help="Override the slot's provider.")
    parser.add_argument("--model", default=None, help="Override the slot's model.")
    parser.add_argument("--max-tokens", type=int, default=2000, help="Output cap.")
    parser.add_argument(
        "--reasoning",
        default="none",
        help="Reasoning level (default: none, what the planner slot uses).",
    )
    parser.add_argument("--languages", default="fr,en,de,es,it,zh", help="Comma-separated.")
    parser.add_argument("--report", type=Path, default=None, help="Write the JSON report here.")
    args = parser.parse_args()

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    families = corpus["families"]
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]

    from src.infrastructure.llm.factory import get_llm

    # A measurement must NAME its model: publishing a percentage without one
    # says nothing anybody can act on, and a slot's model changes underneath.
    if args.model:
        from src.core.llm_agent_config import LLMAgentConfig
        from src.core.reasoning_intent import ReasoningIntent

        llm = get_llm(
            args.slot,
            # `temperature=1.0` and no penalties: a reasoning model refuses
            # any other sampling value. Forcing 0.0 makes the provider answer
            # 400 on `top_p` — measured 2026-09-06; the adapter is right, the
            # ad-hoc override was not.
            config_override=LLMAgentConfig(
                provider=args.provider or "openai",
                model=args.model,
                temperature=1.0,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                max_tokens=args.max_tokens,
                # An EXPLICIT intent, always. Measured 2026-09-06: with none
                # configured, `top_p` survives the adapter's reasoning filter
                # and the provider answers 400 on every call — 108 of them,
                # scored as 108 failures of the model. A measurement that
                # cannot reach the model measures the harness.
                reasoning_effort=ReasoningIntent(level=args.reasoning),
            ),
        )
        measured = f"{args.provider or 'openai'} / {args.model} (reasoning={args.reasoning})"
    else:
        llm = get_llm(args.slot)
        measured = f"slot:{args.slot}"
    print("measuring " + measured)

    rows: list[dict[str, Any]] = []
    for family in families:
        for language in languages:
            if language not in family["utterances"]:
                continue
            expected = _expected_instants(family, corpus)
            try:
                produced = await _ask(llm, family, language, corpus)
                got = _instants_of(produced, family, corpus)
                verdict = "exact" if got == expected else "wrong"
            except Exception as exc:  # a refusal, a bad JSON, a provider error
                produced, got, verdict = {"error": str(exc)[:200]}, [], "unreadable"
            rows.append(
                {
                    "family": family["id"],
                    "language": language,
                    "utterance": family["utterances"][language],
                    "produced": produced,
                    "instants": got,
                    "expected": expected,
                    "verdict": verdict,
                }
            )
            print(f"  {verdict:10} {language}  {family['id']}")

    by_language = Counter((r["language"], r["verdict"]) for r in rows)
    by_family = Counter((r["family"], r["verdict"]) for r in rows)
    exact = sum(1 for r in rows if r["verdict"] == "exact")

    print(f"\n=== {exact}/{len(rows)} exact ({exact * 100 // max(len(rows), 1)}%) ===")
    print("\nby language:")
    for language in languages:
        total = sum(v for (lang, _), v in by_language.items() if lang == language)
        ok = by_language[(language, "exact")]
        if total:
            print(f"  {language:5} {ok:3d}/{total:<3d} {ok * 100 // total:3d}%")
    print("\nfamilies that failed at least once:")
    for family in families:
        wrong = by_family[(family["id"], "wrong")] + by_family[(family["id"], "unreadable")]
        if wrong:
            print(f"  {family['id']:28} {wrong} of {len(languages)}")

    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "measured_at": datetime.now().isoformat(timespec="seconds"),
                    "slot": args.slot,
                    "measured": measured,
                    "exact": exact,
                    "total": len(rows),
                    "rows": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nreport written to {args.report}")

    # Always zero: this is a MEASUREMENT, never a gate. A provider's accuracy
    # is not a build verdict, and making it one would put a paid call on a
    # path someone has to pass to merge.
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
