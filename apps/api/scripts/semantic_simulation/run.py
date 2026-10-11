"""Controlled native planner/ReAct probes, explicitly opted in with --real-models.

Run inside the dev API container: python -m scripts.semantic_simulation.run
--real-models --budget-eur 2 --output /app/.tmp/semantic-real.json
The account's external tools are never invoked; only model spend is persisted.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import TypeAdapter

from scripts.semantic_simulation.analyzer import analyze_case
from scripts.semantic_simulation.corpus import SCENARIOS, Scenario, assess, read_result
from scripts.semantic_simulation.execution import check_arguments, simulate_plan
from scripts.semantic_simulation.prompts import (
    TOOLS,
    manifests_for_case,
    planner_messages,
    react_messages,
    registry_for_probe,
)
from scripts.semantic_simulation.runtime import ProbeRuntime, invoke, prepare
from src.core.context import request_tool_manifests_ctx
from src.domains.agents.analysis.query_intelligence import QueryIntelligence
from src.domains.agents.registry.agent_registry import AgentRegistry

_OBJECT = TypeAdapter(dict[str, object])


async def planner_case(
    runtime: ProbeRuntime,
    scenario: Scenario,
    registry: AgentRegistry,
    intelligence: QueryIntelligence | None = None,
) -> dict[str, object]:
    manifests = manifests_for_case(registry, scenario)
    messages = planner_messages(scenario, manifests, registry, intelligence)
    response = await invoke(runtime, "planner", messages, case=scenario.name)
    result: dict[str, object]
    try:
        result = simulate_plan(scenario, response.text, registry)
    except (ValueError, KeyError, StopIteration) as exc:
        result = {"failures": [f"{type(exc).__name__}: {exc}"]}
    result["raw_response"] = response.text
    return result


def _tool_schemas(names: set[str]) -> list[dict[str, object]]:
    return [
        _OBJECT.validate_python(convert_to_openai_tool(tool.tool_call_schema, strict=False))
        for tool in TOOLS
        if tool.name in names
    ]


async def react_case(
    runtime: ProbeRuntime,
    scenario: Scenario,
    registry: AgentRegistry,
    intelligence: QueryIntelligence | None = None,
) -> dict[str, object]:
    manifests = manifests_for_case(registry, scenario)
    names = {manifest.name for manifest in manifests}
    tools = _tool_schemas(names)
    messages: list[BaseMessage] = react_messages(scenario, manifests, intelligence)
    calls: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []
    for iteration in range(3):
        response = await invoke(runtime, "react_agent", messages, case=scenario.name, tools=tools)
        responses.append(
            {"iteration": iteration + 1, "text": response.text, "tool_calls": response.tool_calls}
        )
        messages.append(response)
        if not response.tool_calls:
            break
        try:
            tool_calls = [_OBJECT.validate_python(call) for call in response.tool_calls]
            if _observe_tools(scenario, tool_calls, messages, calls):
                break
        except (ValueError, KeyError, StopIteration) as exc:
            return {
                "calls": calls,
                "failures": [f"{type(exc).__name__}: {exc}"],
                "responses": responses,
            }
    return {"calls": calls, "failures": assess(scenario, calls), "responses": responses}


def _observe_tools(
    scenario: Scenario,
    tool_calls: list[dict[str, object]],
    messages: list[BaseMessage],
    calls: list[dict[str, object]],
) -> bool:
    action_seen = False
    for call in tool_calls:
        name = str(call["name"])
        arguments = _OBJECT.validate_python(call["args"])
        check_arguments(name, arguments)
        calls.append({"name": name, "arguments": arguments})
        if name == scenario.action:
            action_seen = True
            continue
        observation = read_result(name, scenario)
        messages.append(
            ToolMessage(
                content="<external_content>"
                + json.dumps(observation, ensure_ascii=False)
                + "</external_content>",
                tool_call_id=str(call["id"]),
                name=name,
            )
        )
    return action_seen


def _save(output: Path, report: dict[str, object], runtime: ProbeRuntime) -> None:
    report["cost_eur"] = runtime.spent_eur
    report["provider_calls"] = runtime.calls
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


async def run(
    output: Path,
    *,
    budget_eur: float,
    real_models: bool,
    scenarios: tuple[Scenario, ...] = SCENARIOS,
    with_analyzer: bool = False,
) -> None:
    registry = registry_for_probe()
    if not real_models:
        for scenario in scenarios:
            token = request_tool_manifests_ctx.set(manifests_for_case(registry, scenario))
            try:
                planner_messages(scenario, manifests_for_case(registry, scenario), registry)
                react_messages(scenario)
            finally:
                request_tool_manifests_ctx.reset(token)
        print("Offline preflight passed; no provider call. Use --real-models to opt in.")
        return
    runtime = await prepare(budget_eur)
    report: dict[str, object] = {
        "started_at": datetime.now(UTC).isoformat(),
        "database_environment": "local dev API/PostgreSQL",
        "configuration": runtime.configuration,
        "authorized_budget_eur": budget_eur,
        "scope": "production prompts/schemas; controlled query intelligence and fictional tool observations; no tool effects",
        "results": [],
        "analyzer_evaluated": with_analyzer,
    }
    results: list[dict[str, object]] = []
    report["results"] = results
    _save(output, report, runtime)
    for scenario in scenarios:
        token = request_tool_manifests_ctx.set(manifests_for_case(registry, scenario))
        try:
            intelligence = None
            analysis: dict[str, object] = {}
            if with_analyzer:
                intelligence, analysis = await analyze_case(runtime, scenario)
            for mode in ("planner", "react"):
                try:
                    outcome = (
                        await planner_case(runtime, scenario, registry, intelligence)
                        if mode == "planner"
                        else await react_case(runtime, scenario, registry, intelligence)
                    )
                except Exception as exc:
                    outcome = {"failures": [f"{type(exc).__name__}: {exc}"]}
                    results.append(
                        {
                            "scenario": scenario.name,
                            "query": scenario.query,
                            "expected": scenario.expected,
                            "mode": mode,
                            "analysis": analysis,
                            **outcome,
                        }
                    )
                    _save(output, report, runtime)
                    raise
                results.append(
                    {
                        "scenario": scenario.name,
                        "query": scenario.query,
                        "expected": scenario.expected,
                        "mode": mode,
                        "analysis": analysis,
                        **outcome,
                    }
                )
                _save(output, report, runtime)
                print(
                    json.dumps(
                        {
                            "scenario": scenario.name,
                            "mode": mode,
                            "failures": outcome.get("failures"),
                            "cost_eur": runtime.spent_eur,
                        }
                    ),
                    flush=True,
                )
        finally:
            request_tool_manifests_ctx.reset(token)
    report["finished_at"] = datetime.now(UTC).isoformat()
    _save(output, report, runtime)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-models", action="store_true")
    parser.add_argument("--budget-eur", type=float, default=2.0)
    parser.add_argument("--output", type=Path, default=Path(".tmp/semantic-real.json"))
    parser.add_argument("--case", action="append", choices=[case.name for case in SCENARIOS])
    parser.add_argument("--with-analyzer", action="store_true")
    args = parser.parse_args()
    if not 0 < args.budget_eur <= 2:
        parser.error("budget must be positive and at most the authorized 2 EUR ceiling")
    scenarios = tuple(case for case in SCENARIOS if not args.case or case.name in args.case)
    asyncio.run(
        run(
            args.output,
            budget_eur=args.budget_eur,
            real_models=args.real_models,
            scenarios=scenarios,
            with_analyzer=args.with_analyzer,
        )
    )


if __name__ == "__main__":
    main()
