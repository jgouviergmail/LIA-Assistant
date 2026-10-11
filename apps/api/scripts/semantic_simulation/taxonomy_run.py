"""Evaluate DB-configured analyzer decisions against the full current domain menu."""

import argparse
import asyncio
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ValidationError

from scripts.semantic_simulation.runtime import ProbeRuntime, invoke, prepare
from scripts.semantic_simulation.taxonomy_corpus import (
    TAXONOMY_CASES,
    TaxonomyRoutingCase,
    assess_routing,
)
from scripts.semantic_simulation.taxonomy_fixtures import full_domain_menu
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.prompt_layout import single_call_messages
from src.core.time_utils import get_current_datetime_context
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.analysis.domain_policy import retain_available_domains
from src.domains.agents.services.analysis.query_analysis_schemas import QueryAnalysisOutput
from src.domains.agents.utils.json_parser import extract_json_from_llm_response
from src.infrastructure.llm.output_truncation import is_output_truncated


def _prompt(case: TaxonomyRoutingCase, menu: list[dict[str, str]]) -> str:
    return str(load_prompt("query_analyzer_prompt", version="v1")).format(
        current_datetime=get_current_datetime_context(DEFAULT_USER_DISPLAY_TIMEZONE, case.language),
        available_domains="\n".join(
            f"- **{item['name']}**: {item['description']}" for item in menu
        ),
        available_skills="None",
        connected_peers="None",
        memory_facts="None",
        conversation_history="None",
        user_location="Not available",
        window_size=5,
        user_query=case.query,
    )


async def _decision(
    runtime: ProbeRuntime, case: TaxonomyRoutingCase, menu: list[dict[str, str]]
) -> dict[str, object]:
    schema: dict[str, object] = convert_to_openai_tool(QueryAnalysisOutput, strict=False)
    response = await invoke(
        runtime,
        "query_analyzer",
        single_call_messages(_prompt(case, menu)),
        case=case.name,
        tools=[schema],
        tool_choice="QueryAnalysisOutput",
    )
    if is_output_truncated(response):
        return {"failures": ["output_truncated"]}
    try:
        if response.tool_calls:
            if (
                len(response.tool_calls) != 1
                or response.tool_calls[0]["name"] != "QueryAnalysisOutput"
            ):
                return {"failures": ["invalid_structured_result"]}
            raw = response.tool_calls[0]["args"]
        else:
            parsed = extract_json_from_llm_response(response_text=response.text, expected_type=dict)
            if not parsed.success:
                return {"failures": ["invalid_structured_result"]}
            raw = parsed.data
        result = QueryAnalysisOutput.model_validate(raw)
    except ValidationError:
        return {"failures": ["schema_validation_failed"]}
    primary, secondary = retain_available_domains(
        result.primary_domain, result.secondary_domains, {item["name"] for item in menu}
    )
    failures = assess_routing(
        case,
        primary_domain=primary,
        secondary_domains=secondary,
        is_mutation_intent=result.is_mutation_intent,
    )
    raw_failures = assess_routing(
        case,
        primary_domain=result.primary_domain,
        secondary_domains=result.secondary_domains,
        is_mutation_intent=result.is_mutation_intent,
    )
    return {
        "raw_primary": result.primary_domain,
        "raw_secondary": result.secondary_domains,
        "primary": primary,
        "secondary": secondary,
        "is_mutation_intent": result.is_mutation_intent,
        "intent": result.intent,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "failures": list(failures),
        "raw_failures": list(raw_failures),
        "unavailable_domains": sorted(
            ({result.primary_domain} | set(result.secondary_domains))
            - {None, ""}
            - {item["name"] for item in menu}
        ),
    }


def _save(path: Path, report: dict[str, object], runtime: ProbeRuntime | None) -> None:
    if runtime is not None:
        report["configuration"] = runtime.configuration
        report["calls"] = runtime.calls
        report["cost_eur"] = runtime.spent_eur
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_budget(budget_eur: float, prior_spend: float) -> None:
    if (
        not math.isfinite(budget_eur)
        or not math.isfinite(prior_spend)
        or not 0 < budget_eur <= 2
        or prior_spend < 0
        or budget_eur + prior_spend > 2
    ):
        raise ValueError(
            "Budget plus recorded prior spend must fit the cumulative authorized 2 EUR ceiling"
        )


def select_cases(names: list[str]) -> tuple[TaxonomyRoutingCase, ...]:
    selected = set(names)
    unknown = selected - {case.name for case in TAXONOMY_CASES}
    if unknown:
        raise ValueError("Unknown cases: " + ", ".join(sorted(unknown)))
    return tuple(case for case in TAXONOMY_CASES if not selected or case.name in selected)


def _summary(results: list[dict[str, object]]) -> dict[str, int]:
    evaluated = [result for result in results if "failures" in result]
    return {
        "cases_recorded": len(results),
        "cases_evaluated": len(evaluated),
        "passed": sum(not result["failures"] for result in evaluated),
        "failed": sum(bool(result["failures"]) for result in evaluated),
        "raw_failed": sum(bool(result.get("raw_failures")) for result in evaluated),
        "unavailable_selections": sum(
            bool(result.get("unavailable_domains")) for result in evaluated
        ),
    }


def _source_fingerprints() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    paths = (
        "src/domains/agents/prompts/v1/query_analyzer_prompt.txt",
        "src/domains/agents/registry/domain_taxonomy.py",
        "src/domains/agents/registry/program_domain_configs.py",
        "src/domains/agents/registry/mcp_domain_descriptions.py",
        "scripts/semantic_simulation/taxonomy_corpus.py",
        "scripts/semantic_simulation/taxonomy_run.py",
    )
    return {path: sha256((root / path).read_bytes()).hexdigest() for path in paths}


async def run(
    path: Path,
    *,
    real_models: bool,
    budget_eur: float,
    prior_spend: float,
    cases: tuple[TaxonomyRoutingCase, ...] = TAXONOMY_CASES,
) -> None:
    validate_budget(budget_eur, prior_spend)
    results: list[dict[str, object]] = []
    report: dict[str, object] = {
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "Production analyzer prompt/schema/domain-policy and full native menu; fictional MCP and feature-enabled fixtures. No native tool effects, skills/history/peer directory, router state-machine or external provider validation.",
        "sampling_limit": "One sample per case at database-configured sampling; no statistical optimum or causal before/after model claim.",
        "prior_campaign_cost_eur": prior_spend,
        "budget_eur": budget_eur,
        "results": results,
        "source_sha256": _source_fingerprints(),
    }
    runtime = await prepare(budget_eur) if real_models else None
    _save(path, report, runtime)
    for case in cases:
        with full_domain_menu(case.menu_variant) as menu:
            outcome: dict[str, object] = {}
            if runtime is not None:
                try:
                    outcome = await _decision(runtime, case, menu)
                except Exception as exc:
                    results.append(
                        {
                            "case": asdict(case),
                            "menu": menu,
                            "failures": ["probe_stopped:" + type(exc).__name__],
                        }
                    )
                    report["summary"] = _summary(results)
                    report["cumulative_cost_eur"] = prior_spend + runtime.spent_eur
                    raise
                finally:
                    _save(path, report, runtime)
            results.append({"case": asdict(case), "menu": menu, **outcome})
            report["summary"] = _summary(results)
            _save(path, report, runtime)
            print(
                json.dumps(
                    {
                        "case": case.name,
                        "menu_domains": len(menu),
                        "failures": outcome.get("failures"),
                        "cost_eur": runtime.spent_eur if runtime else 0,
                    }
                ),
                flush=True,
            )
    report["finished_at"] = datetime.now(UTC).isoformat()
    report["cumulative_cost_eur"] = prior_spend + (runtime.spent_eur if runtime else 0)
    _save(path, report, runtime)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-models", action="store_true")
    parser.add_argument("--budget-eur", type=float, default=0.5)
    parser.add_argument("--prior-spend-eur", type=float, required=True)
    parser.add_argument("--output", type=Path, default=Path(".tmp/taxonomy-routing.json"))
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Replay named cases; omission evaluates the whole corpus",
    )
    args = parser.parse_args()
    try:
        validate_budget(args.budget_eur, args.prior_spend_eur)
        cases = select_cases(args.case)
    except ValueError as exc:
        parser.error(str(exc))
    asyncio.run(
        run(
            args.output,
            real_models=args.real_models,
            budget_eur=args.budget_eur,
            prior_spend=args.prior_spend_eur,
            cases=cases,
        )
    )


if __name__ == "__main__":
    main()
