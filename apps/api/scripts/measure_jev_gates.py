"""Paid synthetic qualification of the shipped consultation gate.

Run from apps/api with PYTHONPATH=. Native mode prompts for an ephemeral key. The
initiative utility gate this script also measured was retired on 2026-11-08 (ADR-374).
"""

import argparse
import asyncio
import getpass
import json
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import UUID

import httpx

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.services.planner import jev_consultation
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import NoulQuestion, TypeSafeClient, TypeSafeError


async def native(output, cases, repetitions, key):
    rows = []
    owner = UUID(int=1)
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, key)
        for repeat in range(repetitions):
            for case in cases["consultation"]:
                row = {
                    "suite": "consultation",
                    "id": case["id"],
                    "repeat": repeat,
                    "expected": case.get("expected"),
                }

                async def choose(*, record=row, **kwargs):
                    try:
                        question = kwargs["question"]
                        if isinstance(question, NoulQuestion):
                            batch = await client.choose_many(
                                model="jev-1.13.0",
                                state=kwargs["state"],
                                questions={"selection": question},
                                timeout_seconds=5,
                            )
                            record["answer"] = batch.nouls["selection"].model_dump()
                            record["tokens"] = batch.usage.model_dump()
                            return DecisionAttempt(outcome="success", nouls=batch.nouls)
                        result = await client.choose(
                            model="jev-1.13.0",
                            state=kwargs["state"],
                            question=question,
                            timeout_seconds=5,
                        )
                        record["answer"] = result.answer.model_dump()
                        record["tokens"] = result.usage.model_dump()
                        return DecisionAttempt(outcome="success", answer=result.answer)
                    except TypeSafeError as exc:
                        record["error"] = exc.code
                        if exc.usage is not None:
                            record["tokens"] = exc.usage.model_dump()
                        return DecisionAttempt(outcome=exc.code)

                started = perf_counter()
                qi = QueryIntelligence(
                    original_query=case["query"],
                    english_query=case["query"],
                    immediate_intent="search",
                    immediate_confidence=0.99,
                    user_goal=UserGoal.FIND_INFORMATION,
                    goal_reasoning="Read",
                    domains=[case["domain"]],
                    primary_domain=case["domain"],
                    confidence=0.99,
                    has_temporal_reference=case.get("temporal", False),
                )
                # Access filtering is independently integration-tested. This
                # measurement exercises the real selector on its eligible paths.
                paths = {
                    k: v
                    for k, v in jev_consultation.READ_PATHS.items()
                    if v.domain == case["domain"]
                }
                from src.core.time_utils import now_utc
                from src.domains.agents.services.planner.jev_bounded_consultation import (
                    bounded_paths,
                    wants_bounded_path,
                )

                if wants_bounded_path(qi):
                    paths = bounded_paths(qi, "Europe/Paris", now_utc())
                catalogue = FilteredCatalogue(
                    [{"name": v.tool} for v in paths.values()],
                    len(paths),
                    0,
                    [case["domain"]],
                    ["search"],
                )
                with (
                    patch.object(
                        jev_consultation,
                        "runtime_context_if_running",
                        return_value=LiaRuntimeContext(
                            user_id=owner,
                            thread_id="t",
                            conversation_id="t",
                            timezone="Europe/Paris",
                        ),
                    ),
                    patch.object(jev_consultation, "available_paths", return_value=paths),
                    patch.object(jev_consultation, "choose_with_jev", choose),
                ):
                    result = await jev_consultation.try_consultation_plan(
                        qi, {}, catalogue, journal_context=""
                    )
                selected = result.plan.metadata["jev_path"] if result and result.plan else "other"
                row.update(
                    selected=selected,
                    wrong_accept=selected != "other" and selected != case["expected"],
                )
                row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
                rows.append(row)
                output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "calls": len(rows),
                "wrong_accepted": [row["id"] for row in rows if row.get("wrong_accept")],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parents[1] / "tests/fixtures/jev_gate_cases.json",
    )
    args = parser.parse_args()
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))
    asyncio.run(
        native(args.output, cases, args.repetitions, getpass.getpass("TypeSafe key (not stored): "))
    )
