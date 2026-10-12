"""Run one decision point on one split with the chosen engines; rows are saved case by case.

Inside the dev API container, explicitly opted in (paid):
    python -m scripts.jev_semantic.run --decision d1 --split calibration \
        --engines jev,generative,current --repetitions 3 --ceiling-eur 5
``--dry-run`` builds and validates the corpora and prints the request sizes,
without any call. Results land in /app/.tmp/jev-semantic/.
"""

import argparse
import asyncio
import json
from collections.abc import Mapping
from contextlib import AsyncExitStack, ExitStack
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.jev_semantic import corpus_d1, corpus_d2, corpus_d3, corpus_d4, corpus_d5
from scripts.jev_semantic import questions as q
from scripts.jev_semantic.cases import Case, Split, validate
from scripts.jev_semantic.engines import (
    Answer,
    CurrentEngine,
    GenerativeEngine,
    JevEngine,
    SpendLedger,
)

RESULTS = Path("/app/.tmp/jev-semantic")
VALUE_TYPE_CLASSES = frozenset({"Date", "URL"})


def registry_vocabulary(
    aligned: bool,
) -> tuple[dict[str, str], dict[str, dict[str, str]], dict[str, str | None]]:
    """Concrete types with their published description, by category, and the parent map."""
    from src.domains.agents.semantic.core_types import load_core_types
    from src.domains.agents.semantic.type_registry import get_registry

    registry = get_registry()
    if not len(registry):
        load_core_types(registry)
    concrete: dict[str, str] = {}
    by_category: dict[str, dict[str, str]] = {}
    parents: dict[str, str | None] = {}
    for semantic in registry.get_all():
        name = semantic.name
        parents[name] = semantic.parent
        if not (name[0].islower() or name in VALUE_TYPE_CLASSES):
            continue
        description = str(semantic.description)
        if aligned and name in corpus_d2.CODE_VOCABULARY:
            description = f"{description}. Values: {corpus_d2.CODE_VOCABULARY[name]}."
        concrete[name] = description
        category = str(semantic.category).split(".")[-1]
        by_category.setdefault(category, {})[name] = description
    return concrete, by_category, parents


def build_cases(decision: str, split: Split, menu: list[dict[str, str]] | None) -> tuple[Case, ...]:
    """Build and validate one decision's split."""
    if decision == "d1":
        cases = corpus_d1.build(split)
        validate(cases, corpus_d1.LABELS)
    elif decision == "d2":
        concrete, _, parents = registry_vocabulary(aligned=False)
        cases = corpus_d2.build(split, parents)
        validate(cases, frozenset(parents))
        missing = set(corpus_d2.CASES) - set(concrete)
        uncovered = set(concrete) - set(corpus_d2.CASES)
        if missing or uncovered:
            raise ValueError(
                f"d2 coverage: unknown={sorted(missing)} uncovered={sorted(uncovered)}"
            )
    elif decision == "d3":
        assert menu is not None
        cases = corpus_d3.build(split)
        validate(cases, frozenset(item["name"] for item in menu))
    elif decision == "d4":
        cases = corpus_d4.build(split)
        validate(cases, corpus_d4.LABELS)
    else:
        cases = corpus_d5.build(split)
        validate(cases, corpus_d5.LABELS)
    return cases


def questions_for(
    decision: str, menu: list[dict[str, str]] | None, aligned: bool
) -> dict[str, Any]:
    """The single-stage questions of a decision (d2 flat)."""
    if decision == "d1":
        return q.d1_questions()
    if decision == "d2":
        concrete, _, _ = registry_vocabulary(aligned)
        return q.d2_flat_questions(concrete)
    if decision == "d3":
        assert menu is not None
        return q.d3_questions(menu)
    if decision == "d4":
        return q.d4_questions()
    return q.d5_questions()


async def hierarchical(engine: Any, case: Case, aligned: bool) -> Answer:
    """d2 in two stages: the category, then the type within it."""
    _, by_category, _ = registry_vocabulary(aligned)
    first = await engine.decide(q.d2_category_questions(), case.state, case.id + ":category")
    category = first.labels.get("category")
    if category not in by_category:
        first.error = first.error or "no_category"
        return first
    second = await engine.decide(
        q.d2_type_questions(by_category[category]), case.state, case.id + ":type"
    )
    return Answer(
        labels={"category": category, **second.labels},
        confidence={
            **{f"category_{k}": v for k, v in first.confidence.items()},
            **second.confidence,
        },
        latency_ms=first.latency_ms + second.latency_ms,
        cost_eur=first.cost_eur + second.cost_eur,
        calls=first.calls + second.calls,
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        error=first.error or second.error,
    )


def row(case: Case, engine: str, variant: str, repeat: int, answer: Answer) -> dict[str, object]:
    """One result row, self-describing for the report."""
    return {
        "id": case.id,
        "decision": case.decision,
        "split": case.split,
        "language": case.language,
        "family": case.family,
        "gold": case.gold,
        "accepted": sorted(case.accepted),
        "lenient": sorted(case.lenient),
        "required": sorted(case.required),
        "optional": sorted(case.optional),
        "engine": engine,
        "variant": variant,
        "repeat": repeat,
        **asdict(answer),
    }


def _save(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


async def main(args: argparse.Namespace) -> None:
    """Run the requested engines over the split, saving after every case."""
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.startup.caches import (
        init_config_caches,
        init_pricing_caches,
        init_redis,
    )

    import_all_models()
    engines = [e for e in args.engines.split(",") if e]
    variant = (
        f"{args.d2_mode}-{'aligned' if args.aligned else 'registry'}"
        if args.decision == "d2"
        else "default"
    )
    with ExitStack() as menus:
        menu: list[dict[str, str]] | None = None
        if args.decision == "d3":
            from scripts.semantic_simulation.taxonomy_fixtures import full_domain_menu

            menu = list(menus.enter_context(full_domain_menu("native")))
        cases = build_cases(args.decision, args.split, menu)[: args.limit or None]
        questions = questions_for(args.decision, menu, args.aligned)
        size = len(
            json.dumps(
                {k: v.model_dump() for k, v in questions.items()}, ensure_ascii=False
            ).encode()
        )
        print(
            f"{args.decision}/{args.split}: {len(cases)} cases, {len(questions)} questions, ~{size} bytes of questions"
        )
        if args.dry_run:
            return
        await init_redis()
        await init_pricing_caches()
        await init_config_caches()
        ledger = SpendLedger(RESULTS / "spend.json", args.ceiling_eur)
        output = RESULTS / f"{args.decision}-{args.split}-{variant}-{'-'.join(engines)}.json"
        report: dict[str, object] = {
            "started_at": datetime.now(UTC).isoformat(),
            "decision": args.decision,
            "split": args.split,
            "variant": variant,
            "engines": {},
            "rows": [],
        }
        rows: list[dict[str, object]] = report["rows"]  # type: ignore[assignment]
        async with AsyncExitStack() as stack:
            jev = await stack.enter_async_context(JevEngine(ledger)) if "jev" in engines else None
            needs_generative = "generative" in engines or (
                "current" in engines and args.decision in {"d3", "d4"}
            )
            generative = (
                await stack.enter_async_context(GenerativeEngine(ledger))
                if needs_generative
                else None
            )
            current = CurrentEngine(generative) if "current" in engines else None  # type: ignore[arg-type]
            for engine in (jev, generative, current):
                if engine is not None and (engine is not generative or "generative" in engines):
                    report["engines"][engine.name] = engine.describe()  # type: ignore[index]
            for case in cases:
                for repeat in range(args.repetitions):
                    for engine in (jev, generative if "generative" in engines else None):
                        if engine is None:
                            continue
                        if args.decision == "d2" and args.d2_mode == "hierarchical":
                            answer = await hierarchical(engine, case, args.aligned)
                        else:
                            answer = await engine.decide(questions, case.state, case.id)
                        rows.append(row(case, engine.name, variant, repeat, answer))
                if current is not None and args.decision != "d2":
                    if args.decision == "d1":
                        answer = current.d1(case.state)
                    elif args.decision == "d5":
                        answer = current.d5(case)
                    elif args.decision == "d3":
                        assert menu is not None
                        answer = await current.d3(case, menu)
                    else:
                        answer = await current.d4(case)
                    rows.append(row(case, "current", variant, 0, answer))
                report["spent_eur_cumulative"] = ledger.spent
                _save(output, report)
        print(f"saved {output} — cumulative spend {ledger.spent:.4f} EUR")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=("d1", "d2", "d3", "d4", "d5"), required=True)
    parser.add_argument("--split", choices=("calibration", "independent"), required=True)
    parser.add_argument("--engines", default="jev,generative,current")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--d2-mode", choices=("flat", "hierarchical"), default="flat")
    parser.add_argument(
        "--aligned", action="store_true", help="d2: publish the code's vocabularies"
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--ceiling-eur", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(main(parser.parse_args()))
