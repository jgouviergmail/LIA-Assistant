"""Explicit paid qualification on synthetic complete scripts, never live user records.

Run from apps/api with PYTHONPATH=. and TYPESAFE_API_KEY, or --prompt-key (hidden
console input). The output stores only synthetic case ids, decisions, counters
and latency. Every script keeps its transitions and all cited facts together.
"""

import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

import httpx

from src.domains.radio.facts import FactKind, FactPack, RadioFact, Sensitivity, SourceRef
from src.domains.radio.formats import RadioFormat, RadioRole
from src.domains.radio.jev_checker import MIN_CONFIDENCE, verifier_request
from src.domains.radio.script import LineKind, RadioDelivery, ScriptPart
from src.domains.radio.verification import VerifiedLine
from src.infrastructure.llm.typesafe_client import TypeSafeClient, TypeSafeError


async def measure(output: Path, key: str, repetitions: int, corpus: Path, threshold: float) -> None:
    cases = json.loads(corpus.read_text(encoding="utf-8"))
    records = []
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, key)
        for repeat in range(repetitions):
            for case in cases:
                pack = FactPack(
                    format=RadioFormat.BULLETIN,
                    facts=tuple(
                        RadioFact(
                            **fact,
                            key=f"synthetic:{fact['id']}",
                            kind=FactKind.NEWS,
                            sensitivity=Sensitivity.PUBLIC,
                            source=SourceRef(label="Example News"),
                        )
                        for fact in case["facts"]
                    ),
                )
                lines = tuple(
                    VerifiedLine(
                        RadioRole.ANCHOR,
                        ScriptPart.BODY,
                        LineKind(line["kind"]),
                        line["text"],
                        RadioDelivery(),
                        tuple(line["refs"]),
                    )
                    for line in case["lines"]
                )
                request = verifier_request(lines, pack, "Radio 42")
                assert request is not None
                started = perf_counter()
                row = {"id": case["id"], "repeat": repeat, "expected": case["expected_unsupported"]}
                try:
                    result = await client.choose_many(
                        model="jev-1.13.0",
                        state=request[0],
                        questions=request[1],
                        timeout_seconds=5,
                    )
                    accepted = all(
                        answer.confidence >= threshold and answer.choice != "unknown"
                        for answer in result.answers.values()
                    )
                    predicted = [
                        index
                        for index in range(len(lines))
                        if f"line{index}" in result.answers
                        and result.answers[f"line{index}"].choice == "unsupported"
                    ]
                    row.update(
                        accepted=accepted,
                        predicted=predicted,
                        correct=predicted == case["expected_unsupported"],
                        answers={
                            name: answer.model_dump() for name, answer in result.answers.items()
                        },
                        tokens=result.usage.model_dump(),
                        model=result.model,
                    )
                except TypeSafeError as exc:
                    row.update(accepted=False, error=exc.code)
                    if exc.usage is not None:
                        row["tokens"] = exc.usage.model_dump()
                row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
                records.append(row)
                output.write_text(
                    json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
    accepted = [row for row in records if row.get("accepted")]
    print(
        json.dumps(
            {
                "scripts": len(records),
                "accepted": len(accepted),
                "wrong_accepted": sum(not row["correct"] for row in accepted),
                "fallback": len(records) - len(accepted),
                "median_ms": median(row["latency_ms"] for row in records),
                "input_tokens": sum(
                    row.get("tokens", {}).get("input_tokens", 0) for row in records
                ),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parents[1] / "tests/fixtures/jev_radio_cases.json",
    )
    parser.add_argument("--threshold", type=float, choices=(0.95, 0.99), default=MIN_CONFIDENCE)
    args = parser.parse_args()
    credential = (
        getpass.getpass("TypeSafe key (not stored): ")
        if args.prompt_key
        else os.environ["TYPESAFE_API_KEY"]
    )
    asyncio.run(measure(args.output, credential, args.repetitions, args.corpus, args.threshold))
