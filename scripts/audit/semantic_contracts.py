#!/usr/bin/env python3
"""Measure native semantic contracts without a database, network or MCP call.

Run with the API interpreter from the repository root:
    apps/api/.venv/Scripts/python.exe scripts/audit/semantic_contracts.py --output report.json

The report includes every optional/split native manifest, untyped fields and
producer/consumer paths. Dynamic MCP coverage depends on each server's declared
schema and is verified separately by the MCP contract tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.agents.semantic.type_registry import TypeRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


def ontology_stats(registry: TypeRegistry, used_types: set[str]) -> dict[str, int]:
    """Measure ontology declarations independently from tool-field coverage."""
    registered = {type_def.name for type_def in registry.get_all()}
    return {
        "ontology_types": len(registry),
        "ontology_properties": sum(
            len(type_def.properties) for type_def in registry.get_all()
        ),
        "annotated_ontology_types": len(used_types & registered),
    }


def inventory() -> dict[str, object]:
    """Return counts plus reviewable field-level provenance, never guessed types."""
    from src.domains.agents.registry.semantic_inventory import collect_static_manifests
    from src.domains.agents.semantic.core_types import load_core_types
    from src.domains.agents.semantic.manifest_semantics import parameter_semantic_types
    from src.domains.agents.semantic.type_registry import TypeRegistry

    manifests = collect_static_manifests()
    registry = TypeRegistry()
    load_core_types(registry)
    rows: list[dict[str, object]] = []
    domains: dict[str, dict[str, int]] = {}
    producers: dict[str, list[str]] = {}
    consumers: dict[str, list[str]] = {}
    unknown: list[str] = []
    for manifest in manifests:
        domain = manifest.agent.removesuffix("_agent")
        counts = domains.setdefault(
            domain,
            {
                "tools": 0,
                "parameters": 0,
                "typed_parameters": 0,
                "outputs": 0,
                "typed_outputs": 0,
            },
        )
        counts["tools"] += 1
        entries = [
            (
                "parameter",
                field.name,
                field.type,
                field.semantic_type,
                parameter_semantic_types(field),
            )
            for field in manifest.parameters
        ] + [
            (
                "output",
                field.path,
                field.type,
                field.semantic_type,
                {field.semantic_type} if field.semantic_type else set(),
            )
            for field in manifest.outputs
        ]
        for kind, name, json_type, semantic_type, types in entries:
            plural = "parameters" if kind == "parameter" else "outputs"
            counts[plural] += 1
            counts[f"typed_{plural}"] += bool(semantic_type)
            reference = f"{manifest.name}:{name}"
            for type_name in sorted(types):
                index = consumers if kind == "parameter" else producers
                index.setdefault(type_name, []).append(reference)
                if type_name not in registry:
                    unknown.append(f"{reference}: {type_name}")
            rows.append(
                {
                    "tool": manifest.name,
                    "domain": domain,
                    "kind": kind,
                    "field": name,
                    "json_type": json_type,
                    "semantic_type": semantic_type,
                    "nested_types": sorted(types),
                }
            )
    totals = {
        key: sum(counts[key] for counts in domains.values())
        for key in (
            "tools",
            "parameters",
            "typed_parameters",
            "outputs",
            "typed_outputs",
        )
    }
    return {
        "scope": "all declared native manifests; MCP is discovered per request",
        "totals": totals,
        "domains": dict(sorted(domains.items())),
        **ontology_stats(registry, producers.keys() | consumers.keys()),
        "ontology_errors": registry.validate_hierarchy(),
        "unknown_annotations": sorted(unknown),
        "types": {
            name: {
                "producers": producers.get(name, []),
                "consumers": consumers.get(name, []),
            }
            for name in sorted(producers.keys() | consumers.keys())
        },
        "fields": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the full JSON inventory")
    args = parser.parse_args()
    report = inventory()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "totals",
                        "ontology_types",
                        "ontology_properties",
                        "annotated_ontology_types",
                        "ontology_errors",
                        "unknown_annotations",
                    )
                },
                indent=2,
            )
        )
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["ontology_errors"] or report["unknown_annotations"]))


if __name__ == "__main__":
    raise SystemExit(main())
