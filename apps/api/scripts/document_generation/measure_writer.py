"""Measure the document writer on real models (ADR-274, ADR-388) — PAID, on demand.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. Each
scenario of ``writer_scenarios.json`` is a request and its material, as the agent
hands them to the tool, and runs through the production's own door —
``service._call_document_llm``: its prompt, its schema, its structured output and
its retries — on the model passed, pointed at in THIS process only (the slot's
in-memory override: the database is never written, there is nothing to restore).
The answer is normalized and rendered as production does, every picture drawn
flat: no image is generated. Each run reports:

- what it cost: model calls (a refused answer is paid again), tokens, USD, seconds;
- whether the writer kept the rules the prompt publishes: a presented deck
  declared so, key figures where the material has them and every figure's
  number found in that material, every source's address copied from it (an
  invented address is the defect sources exist to avoid), pictures within the
  budget and none where none may be asked;
- what normalization had to repair: words off a closed vocabulary, computed
  columns and key figures whose formula it refused;
- whether the result renders.

It prints counts and flags, never the document. It runs on the PROOF account
(``scripts/proof_account.py``), whose ceilings bound it, and stops past
``--budget`` USD. Run inside the API container, which holds the model
configuration, the provider keys and the tariffs::

    python -m scripts.document_generation.measure_writer --models provider:model@level --budget 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.callbacks import AsyncCallbackHandler  # noqa: E402
from langchain_core.outputs import LLMResult  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from scripts.llm_families import named_families, prepare_bench  # noqa: E402
from scripts.proof_account import proof_user  # noqa: E402
from src.core.constants import (  # noqa: E402
    DEFAULT_USER_DISPLAY_TIMEZONE,
    DOCUMENT_GENERATION_LLM_TYPE,
)
from src.core.document_preferences import DocumentPreferences, document_preferences  # noqa: E402
from src.core.reasoning_intent import Level  # noqa: E402
from src.domains.document_generation import service  # noqa: E402
from src.domains.document_generation.columns import column_key  # noqa: E402
from src.domains.document_generation.context import build_render_context  # noqa: E402
from src.domains.document_generation.formulas import FormulaError, parse_formula  # noqa: E402
from src.domains.document_generation.normalize import (  # noqa: E402
    document_is_numbered,
    normalize_content,
)
from src.domains.document_generation.pictures import illustration_budget  # noqa: E402
from src.domains.document_generation.renderers import render_document  # noqa: E402
from src.domains.document_generation.schemas import (  # noqa: E402
    BETTER_DIRECTIONS,
    CHART_FORMS,
    CHART_INTENTS,
    COLUMN_KINDS,
    DECK_DELIVERIES,
    DOCUMENT_TONES,
    FIGURE_KINDS,
    SLIDE_ICONS,
    SUMMARY_FUNCTIONS,
    TOTAL_FUNCTIONS,
    DocumentContent,
    DocumentType,
    SectionedContent,
    SlideContent,
    TabularContent,
)
from src.domains.document_generation.workbook_figures import parse_figure  # noqa: E402
from src.domains.llm_config.cache import LLMConfigOverrideCache  # noqa: E402
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur  # noqa: E402
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.factory import clear_llm_instance_cache  # noqa: E402
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata  # noqa: E402
from src.infrastructure.observability.metrics_errors import (  # noqa: E402
    llm_structured_output_outcomes_total,
)
from tests.helpers.document_pictures import synthetic_pictures  # noqa: E402

SCENARIOS_FILE = Path(__file__).with_name("writer_scenarios.json")
#: A number of a text, digits joined across the separators prose and locales use.
_NUMBER = re.compile(r"\d+(?:[.,   ]\d+)*")
_CITATION = re.compile(r"\[\d+\]")
#: How much of an unanchored figure the report keeps: a value, never a sentence.
_VALUE_MAX_CHARS = 24
#: How much of a refused formula the report keeps.
_FORMULA_MAX_CHARS = 80
#: The closed vocabularies a writer is published, by the field that carries them.
_VOCABULARY: dict[str, frozenset[str]] = {
    "tone": frozenset(DOCUMENT_TONES),
    "delivery": frozenset(DECK_DELIVERIES),
    "icon": frozenset(SLIDE_ICONS),
    "intent": frozenset(CHART_INTENTS),
    "form": frozenset(CHART_FORMS),
    "total": frozenset(TOTAL_FUNCTIONS),
    "better": frozenset(BETTER_DIRECTIONS),
    "function": frozenset(SUMMARY_FUNCTIONS),
}
#: Lists whose items' ``kind`` is a column's or a workbook key figure's, and the words
#: each is offered (the block and slide kinds are validated).
_KIND_LISTS: dict[str, frozenset[str]] = {
    "columns": frozenset(COLUMN_KINDS),
    "inputs": frozenset(FIGURE_KINDS),
    "figures": frozenset(FIGURE_KINDS),
}


@dataclass(frozen=True, slots=True)
class Scenario:
    """A request, its material, and what the rules make of it."""

    key: str
    doc_type: DocumentType
    language: str
    illustrations: str
    instructions: str
    source_data: str
    expect: Mapping[str, Any]


@dataclass
class Run:
    """What one scenario run cost and did."""

    model: str
    scenario: str
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str | None = None
    budget: int = 0
    pictures_asked: int = 0
    pictures_kept: int = 0
    delivery: str = ""
    figures: int = 0
    unanchored_figures: int = 0
    #: The figures whose number the material does not hold — a scenario's own
    #: synthetic tokens, never a person's words.
    unanchored_values: list[str] = field(default_factory=list)
    sources: int = 0
    invented_urls: int = 0
    citations: int = 0
    #: Every formula declared: a computed column's, and a workbook key figure's.
    formulas_asked: int = 0
    formulas_kept: int = 0
    #: The workbook key figures the canonical workbook keeps (ADR-388).
    workbook_figures: int = 0
    refused_formulas: list[str] = field(default_factory=list)
    #: The columns delivered with no value — neither written nor computed — as
    #: ``sheet/column``: a template's are empty on purpose, a scenario giving its
    #: data has none.
    empty_columns: list[str] = field(default_factory=list)
    charts: int = 0
    long: bool = False
    vocabulary_misses: list[str] = field(default_factory=list)
    rendered_bytes: int = 0
    verdicts: dict[str, bool] = field(default_factory=dict)
    #: How the structured-output door settled the run's answers, when not by the
    #: provider's own parse: a mechanical repair, or a refusal (ADR-388).
    repairs: dict[str, int] = field(default_factory=dict)


class _Tally(AsyncCallbackHandler):
    """Every model call the door makes — a refused answer is paid again — and its usage."""

    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.prompt = 0
        self.completion = 0
        self.cached = 0
        self.cache_write = 0

    async def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[Any]], **kwargs: Any
    ) -> None:
        self.calls += 1

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for generation in generations:
                message = getattr(generation, "message", None)
                usage = tokens_from_usage_metadata(getattr(message, "usage_metadata", None))
                self.prompt += usage.prompt
                self.completion += usage.completion
                self.cached += usage.cached
                self.cache_write += usage.cache_write


_ORIGINAL_OVERRIDE = LLMConfigOverrideCache.get_override
_POINTED: dict[str, Any] = {}


def _pointed_override(llm_type: str) -> dict[str, Any] | None:
    found = _ORIGINAL_OVERRIDE(llm_type)
    if llm_type != DOCUMENT_GENERATION_LLM_TYPE or not _POINTED:
        return found
    return {**(found or {}), **_POINTED}


def _point_the_slot(provider: str, model: str, level: Level) -> None:
    """THIS process's document slot runs the measured model; the database is never written.

    Every reader of a slot asks ``LLMConfigOverrideCache.get_override`` (the
    factory, the provider lookup, the prompt's length budget): the one seam a
    measurement replaces, in its own process.
    """
    _POINTED.clear()
    _POINTED.update(
        provider=provider,
        model=model,
        reasoning_effort={"level": level, "budget_tokens": None, "exclude_from_output": True},
    )
    LLMConfigOverrideCache.get_override = staticmethod(_pointed_override)  # type: ignore[method-assign]  # a measurement's own seam
    clear_llm_instance_cache()


def _numbers(text: str) -> set[str]:
    """Every number of a text by its digits alone: « 12,4 M€ » and « 12.4M » read alike."""
    return {re.sub(r"\D", "", found) for found in _NUMBER.findall(text)}


def _walk(value: Any, parent: str = "") -> Iterator[tuple[str, str, Any]]:
    """Every (list it stands in, key, value) of a dumped content, depth first."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield parent, key, item
            yield from _walk(item, key if isinstance(item, list) else parent)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item, parent)


def _vocabulary_misses(raw: BaseModel) -> list[str]:
    """Every closed-vocabulary word the writer gave that normalization had to repair."""
    misses: list[str] = []
    for parent, key, value in _walk(raw.model_dump()):
        if not isinstance(value, str) or not value:
            continue
        allowed = _KIND_LISTS.get(parent) if key == "kind" else _VOCABULARY.get(key)
        if allowed is not None and value.strip().casefold() not in allowed:
            misses.append(f"{key}:{value[:40]}")
    return misses


def _refused_formulas(content: DocumentContent) -> list[str]:
    """Each declared formula the grammar refuses, by the grammar's own reason.

    The formula is the writer's text about a scenario's synthetic data, kept short.
    A formula the grammar accepts can still be dropped later (a text operand, a
    cycle): the report's kept count says so.
    """
    if not isinstance(content, TabularContent):
        return []
    inputs = [item.name for item in content.inputs]
    refused: list[str] = []
    sheets: dict[str, list[str]] = {}
    for sheet in content.sheets:
        headers = [*sheet.headers]
        headers += [column.header for column in sheet.columns if column.header not in headers]
        sheets[sheet.name] = headers
        for column in sheet.columns:
            if not column.formula:
                continue
            try:
                parse_formula(column.formula, columns=headers, inputs=inputs, itself=column.header)
            except FormulaError as error:
                refused.append(f"{error.reason}: {column.formula[:_FORMULA_MAX_CHARS]}")
    labels = [figure.label for figure in content.figures]
    for figure in content.figures:
        if not figure.formula.strip():
            continue
        try:
            parse_figure(figure, labels=labels, inputs=inputs, sheets=sheets)
        except FormulaError as error:
            refused.append(f"figure {error.reason}: {figure.formula[:_FORMULA_MAX_CHARS]}")
    return refused


def _figures_of(content: DocumentContent) -> list[str]:
    if isinstance(content, SlideContent):
        return [figure.value for slide in content.slides for figure in slide.figures]
    if isinstance(content, SectionedContent):
        return [figure.value for block in content.blocks for figure in block.figures]
    return []


def _pictures_of(content: DocumentContent) -> int:
    cover = 1 if getattr(content, "illustration", None) is not None else 0
    if isinstance(content, SlideContent):
        return cover + sum(slide.illustration is not None for slide in content.slides)
    if isinstance(content, SectionedContent):
        return cover + sum(block.illustration is not None for block in content.blocks)
    return 0


def _formulas_of(content: DocumentContent) -> int:
    if not isinstance(content, TabularContent):
        return 0
    columns = sum(bool(column.formula) for sheet in content.sheets for column in sheet.columns)
    return columns + sum(bool(figure.formula.strip()) for figure in content.figures)


def _charts_of(content: DocumentContent) -> int:
    if isinstance(content, TabularContent):
        return sum(sheet.chart is not None for sheet in content.sheets)
    if isinstance(content, SlideContent):
        return sum(
            slide.kind == "chart" or (slide.table is not None and slide.table.chart is not None)
            for slide in content.slides
        )
    if isinstance(content, SectionedContent):
        return sum(
            block.kind == "chart" or (block.table is not None and block.table.chart is not None)
            for block in content.blocks
        )
    return 0


def _texts_of(content: SectionedContent) -> str:
    return " ".join(" ".join([block.text, *block.items, block.caption]) for block in content.blocks)


def _empty_columns(content: DocumentContent) -> list[str]:
    """The columns a canonical workbook delivers with no value: neither written nor computed.

    The names are a scenario's synthetic headers, kept short.
    """
    if not isinstance(content, TabularContent):
        return []
    empty: list[str] = []
    for sheet in content.sheets:
        computed = {column_key(spec.header) for spec in sheet.columns if spec.formula}
        for index, header in enumerate(sheet.headers):
            if column_key(header) in computed:
                continue
            if all(not row[index].strip() for row in sheet.rows):
                empty.append(f"{sheet.name}/{header}"[:_VALUE_MAX_CHARS])
    return empty


def _verdicts(run: Run, expect: Mapping[str, Any]) -> dict[str, bool]:
    """What the rules make of the request, held against what the writer did."""
    verdicts = {
        "no_invented_url": run.invented_urls == 0,
        "pictures_within_budget": run.pictures_asked <= run.budget,
        "figures_from_material": run.unanchored_figures == 0,
        "renders": run.rendered_bytes > 0,
    }
    if "delivery" in expect:
        verdicts["delivery"] = run.delivery == expect["delivery"]
    if "figures" in expect:
        verdicts["figures"] = (run.figures > 0) is bool(expect["figures"])
    if "pictures" in expect:
        verdicts["pictures"] = run.pictures_asked == expect["pictures"]
    if expect.get("sources") is True:
        verdicts["sources"] = run.sources > 0 and run.citations > 0
    elif expect.get("sources") is False:
        verdicts["sources"] = run.sources == 0
    if "formulas" in expect:
        verdicts["formulas"] = run.formulas_kept > 0 and run.formulas_kept == run.formulas_asked
    if "chart" in expect:
        verdicts["chart"] = run.charts > 0
    if expect.get("complete") is True:
        verdicts["complete"] = not run.empty_columns
    if "long" in expect:
        verdicts["long"] = run.long
    return verdicts


def _judge(run: Run, scenario: Scenario, raw: DocumentContent, wanted: DocumentPreferences) -> None:
    """Read what the writer produced, then normalize and render it as production does."""
    material = _numbers(scenario.source_data)
    figures = _figures_of(raw)
    run.figures = len(figures)
    run.unanchored_values = [
        value[:_VALUE_MAX_CHARS]
        for value in figures
        if any(number not in material for number in _numbers(value))
    ]
    run.unanchored_figures = len(run.unanchored_values)
    run.pictures_asked = _pictures_of(raw)
    run.budget = illustration_budget(wanted)
    run.formulas_asked = _formulas_of(raw)
    run.refused_formulas = _refused_formulas(raw)
    run.charts = _charts_of(raw)
    run.vocabulary_misses = _vocabulary_misses(raw)
    if isinstance(raw, SlideContent):
        run.delivery = raw.delivery
    if isinstance(raw, SectionedContent):
        run.sources = len(raw.sources)
        run.invented_urls = sum(
            bool(source.url.strip()) and source.url.strip() not in scenario.source_data
            for source in raw.sources
        )
        run.citations = len(_CITATION.findall(_texts_of(raw)))
    context = build_render_context(
        language=scenario.language,
        timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
        generated_at=datetime.now(UTC),
        preferences=wanted,
    )
    canonical = normalize_content(raw, context)
    run.pictures_kept = _pictures_of(canonical)
    run.formulas_kept = _formulas_of(canonical)
    if isinstance(canonical, TabularContent):
        run.workbook_figures = len(canonical.figures)
    run.empty_columns = _empty_columns(canonical)
    if isinstance(canonical, SectionedContent):
        run.long = document_is_numbered(canonical, context)
    try:
        pictured = replace(context, pictures=synthetic_pictures(canonical))
        run.rendered_bytes = len(render_document(scenario.doc_type, canonical, pictured))
    except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
        run.error = f"render:{type(exc).__name__}"


def _outcomes() -> Counter[str]:
    """Every structured-output outcome counted so far, by outcome (the door's own counter)."""
    seen: Counter[str] = Counter()
    for metric in llm_structured_output_outcomes_total.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total"):
                seen[sample.labels["outcome"]] += int(sample.value)
    return seen


async def _run(scenario: Scenario, model: str, label: str, user_id: UUID) -> Run:
    """One scenario on the pointed model, through the production's own door.

    Args:
        scenario: The request and its material.
        model: The model's name, which its tariff is read under.
        label: The model and its reasoning level, as the report names the run.
        user_id: The proof account, whose ceilings bound the call.

    Returns:
        What the run cost and did.
    """
    run = Run(model=label, scenario=scenario.key)
    wanted = service._for_format(
        document_preferences(
            illustrations=scenario.illustrations, animations=None, images_allowed=True
        ),
        scenario.doc_type,
    )
    tally = _Tally()
    before = _outcomes()
    started = time.perf_counter()
    raw: DocumentContent | None = None
    try:
        raw = await service._call_document_llm(
            doc_type=scenario.doc_type,
            instructions=scenario.instructions,
            source_data=scenario.source_data,
            language=scenario.language,
            config={"callbacks": [tally]},
            user_id=user_id,
            preferences=wanted,
        )
    except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
        run.error = type(exc).__name__
    run.seconds = round(time.perf_counter() - started, 1)
    run.repairs = {
        outcome: count for outcome, count in (_outcomes() - before).items() if outcome != "parsed"
    }
    run.calls = tally.calls
    run.tokens_in, run.tokens_out, run.tokens_cached = tally.prompt, tally.completion, tally.cached
    run.cost_usd = get_cached_cost_usd_eur(
        model, tally.prompt, tally.completion, tally.cached, cache_write_tokens=tally.cache_write
    )[0]
    if raw is not None:
        _judge(run, scenario, raw, wanted)
        run.verdicts = _verdicts(run, scenario.expect)
    return run


def _scenarios(wanted: set[str] | None) -> list[Scenario]:
    raw = json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))
    return [
        Scenario(
            key=item["key"],
            doc_type=DocumentType(item["doc_type"]),
            language=item["language"],
            illustrations=item["illustrations"],
            instructions=item["instructions"],
            source_data=item["source_data"],
            expect=item.get("expect", {}),
        )
        for item in raw
        if wanted is None or item["key"] in wanted
    ]


def _summary(runs: list[Run]) -> str:
    rows = [
        "| model | scenario | n | errors | calls/run | USD/run | s/run | out tok/run | rules kept |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str], list[Run]] = {}
    for run in runs:
        groups.setdefault((run.model, run.scenario), []).append(run)
    for (model, scenario), group in groups.items():
        kept = sum(sum(r.verdicts.values()) for r in group)
        total = sum(len(r.verdicts) for r in group)
        rows.append(
            f"| {model} | {scenario} | {len(group)} | {sum(bool(r.error) for r in group)} "
            f"| {statistics.mean(r.calls for r in group):.1f} "
            f"| {statistics.mean(r.cost_usd for r in group):.4f} "
            f"| {statistics.mean(r.seconds for r in group):.0f} "
            f"| {statistics.mean(r.tokens_out for r in group):.0f} "
            f"| {kept}/{total} |"
        )
    return "\n".join(rows)


async def _amain(args: argparse.Namespace) -> int:
    models = named_families(args.models)
    scenarios = _scenarios(set(args.scenario.split(",")) if args.scenario else None)
    if args.dry_run:
        for scenario in scenarios:
            print(scenario.key, scenario.doc_type.value, sorted(scenario.expect))
        return 0
    await prepare_bench()
    async with get_db_context() as db:
        user_id = (await proof_user(db)).id
    runs: list[Run] = []
    spent = 0.0
    started = time.perf_counter()
    for provider, model, level in models:
        _point_the_slot(provider, model, level)
        for scenario in scenarios:
            for _ in range(args.reps):
                if spent > args.budget:  # every remaining run is skipped, none is cut
                    break
                run = await _run(scenario, model, f"{model}@{level}", user_id)
                runs.append(run)
                spent += run.cost_usd
                print(json.dumps(asdict(run), ensure_ascii=False), flush=True)
    if spent > args.budget:
        print(f"stopped: {args.budget} USD reached", file=sys.stderr)
    report = {
        "runs": [asdict(r) for r in runs],
        "cost_usd": round(spent, 4),
        "seconds": round(time.perf_counter() - started, 1),
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(runs))
    print(json.dumps({key: report[key] for key in ("cost_usd", "seconds")}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True, help="provider:model[@level],... (level: a ReasoningIntent)"
    )
    parser.add_argument("--budget", type=float, required=True, help="Stop past this many USD")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--scenario", help="Comma-separated scenario keys (default: all)")
    parser.add_argument("--out", type=Path, help="Write the full report (counts only) here")
    parser.add_argument("--dry-run", action="store_true", help="List the scenarios and stop")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
