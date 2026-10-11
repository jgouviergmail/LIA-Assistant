"""Regrade recorded concrete calls with one oracle, without any provider call."""

import argparse
import json
from pathlib import Path

from scripts.semantic_simulation.corpus import SCENARIOS, assess


def summarize(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    cases = {case.name: case for case in SCENARIOS}
    results: list[dict[str, object]] = []
    for recorded in report["results"]:
        original = recorded.get("failures", [])
        calls = recorded.get("calls")
        # An old validation/execution failure remains a failure: never replay an
        # old plan through the fixed executor and label that a baseline success.
        failures = assess(cases[recorded["scenario"]], calls) if calls else original
        results.append(
            {
                "scenario": recorded["scenario"],
                "mode": recorded["mode"],
                "original_failures": original,
                "comparable_failures": failures,
            }
        )
    return {
        "phase": path.stem,
        "scope": report["scope"],
        "analyzer_evaluated": report.get("analyzer_evaluated", False),
        "configuration": report["configuration"],
        "provider_calls": len(report["provider_calls"]),
        "cost_eur": report["cost_eur"],
        "original_successes": sum(not row["original_failures"] for row in results),
        "comparable_successes": sum(not row["comparable_failures"] for row in results),
        "decisions": len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    phases = [summarize(path) for path in arguments.inputs]
    output = {
        "measured_on": "2026-10-06",
        "oracle": "Exact content/identity/precision; documented ISO date/datetime contract; comma whitespace ignored; explicitly listed fictional address aliases accepted equally in every phase.",
        "scope": "Real DB-configured model decisions; narrowed native catalogues and fictional observations. No native external effects or full router/tool-selection evaluation.",
        "statistical_limit": "One sample per case/mode/phase with configured sampling, no statistical confidence or causal performance claim.",
        "phases": phases,
        "cost_eur": sum(_number(phase["cost_eur"]) for phase in phases),
        "provider_calls": sum(_number(phase["provider_calls"]) for phase in phases),
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")


def _number(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError("Recorded usage is not numeric")
    return float(value)


if __name__ == "__main__":
    main()
