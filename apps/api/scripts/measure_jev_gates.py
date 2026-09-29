"""Paid synthetic qualification of the shipped consultation and initiative gates.

Run from apps/api with PYTHONPATH=. Native mode prompts for an ephemeral key.
--baseline-initiative runs explicitly in the configured dev API container, reads
only LLM configuration and uses the shipped full initiative prompt and schema.
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
from src.domains.agents.nodes import jev_initiative
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.planner import jev_consultation
from src.domains.agents.services.smart_catalogue_service import FilteredCatalogue
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import TypeSafeClient, TypeSafeError


def initiative_prompt(case):
    return load_prompt("initiative_prompt", version="v1").format(
        execution_summary=case["results"],
        original_query=case["query"],
        memory_facts=case["memory"] or "No relevant memories.",
        user_interests="No known interests.",
        available_tools="get_route_tool: read a route between exact locations. get_events_tool: read calendar events. get_weather_forecast_tool: read forecast for an exact place and date.",
        semantic_dependencies="Physical events may require route checks.",
        connection_candidates="Locations and dates in the verified results.",
        user_language="English",
        user_timezone="Europe/Paris",
        current_datetime="2026-09-29T12:00:00+02:00",
        max_actions=3,
    )


async def baseline(output, cases, repetitions):
    from sqlalchemy import text

    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.prompt_layout import single_call_messages
    from src.domains.agents.nodes.initiative_schemas import InitiativeDecision
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database import get_db_context
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.llm.factory import get_llm
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
    from src.infrastructure.llm.structured_output import get_structured_output

    import_all_models()
    async with get_db_context() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    config = get_llm_config_for_agent(settings, "initiative")
    rows = []
    for repeat in range(repetitions):
        for case in cases["initiative"]:
            row = {"suite": "initiative", "id": case["id"], "repeat": repeat, "model": config.model}
            started = perf_counter()
            try:
                result = await get_structured_output(
                    get_llm("initiative"),
                    single_call_messages(initiative_prompt(case)),
                    InitiativeDecision,
                    provider=config.provider,
                    node_name="initiative",
                )
                row["utility"] = bool(
                    result.actions or result.suggestion or result.followup_suggestions
                )
                row["result"] = result.model_dump()
            except Exception as exc:
                row["error"] = type(exc).__name__
            row["latency_ms"] = round((perf_counter() - started) * 1000, 2)
            rows.append(row)
            output.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"calls": len(rows), "errors": sum("error" in row for row in rows)}))


async def native(output, cases, repetitions, key):
    rows = []
    owner = UUID(int=1)
    async with httpx.AsyncClient() as http:
        client = TypeSafeClient(http, key)
        for repeat in range(repetitions):
            for suite in ("consultation", "initiative"):
                for case in cases[suite]:
                    row = {
                        "suite": suite,
                        "id": case["id"],
                        "repeat": repeat,
                        "expected": case.get("expected", case.get("utility")),
                    }

                    async def choose(*, record=row, **kwargs):
                        try:
                            result = await client.choose(
                                model="jev-1.13.0",
                                state=kwargs["state"],
                                question=kwargs["question"],
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
                    if suite == "initiative":
                        with patch.object(jev_initiative, "choose_with_jev", choose):
                            result = await jev_initiative.choose_empty_initiative(
                                initiative_prompt(case), str(owner), "synthetic"
                            )
                        row["skipped"] = result is not None
                        row["wrong_skip"] = result is not None and case["utility"]
                    else:
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
                        selected = (
                            result.plan.metadata["jev_path"] if result and result.plan else "other"
                        )
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
                "wrong_accepted": [
                    row["id"] for row in rows if row.get("wrong_accept") or row.get("wrong_skip")
                ],
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, choices=(1, 2), default=2)
    parser.add_argument("--baseline-initiative", action="store_true")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).parents[1] / "tests/fixtures/jev_gate_cases.json",
    )
    args = parser.parse_args()
    cases = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.baseline_initiative:
        asyncio.run(baseline(args.output, cases, args.repetitions))
    else:
        asyncio.run(
            native(
                args.output, cases, args.repetitions, getpass.getpass("TypeSafe key (not stored): ")
            )
        )
