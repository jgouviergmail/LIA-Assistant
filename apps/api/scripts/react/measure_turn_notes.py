"""Measure how a ReAct loop takes the person's note (ADR-385) — real models, stubbed tools.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. Every
scenario runs through a loop built from the SAME functions as the production node —
the ReAct system prompt (``build_system_prompt``), the stamp of the person's messages
(``with_written_at``), a note's record and its place (``note_record``, ``notes_shown``,
``with_shown``) — while every tool is a deterministic stub. The note joins after the
loop's first tool results, as a person adding it then would, and every later call is
shown it where it arrived:

- ``sunday``: places served with their opening days; the note asks for the ones open
  on Sunday only;
- ``city``: the forecast asked for one city; the note moves the request to another;
- ``dog``: a packing list for a weekend; the note adds a dog.

A run is judged on what can be checked without reading intent: whether every call
after the note was ANSWERED (a provider that refused the shape is the failure this
measures first), whether the answer the person would read FOLLOWS the note (its
``<thought>`` blocks removed: every name or value the note makes necessary, the call
it makes necessary after it, and — when the answer still names what the note
excludes — the word that says why, « closed on Sunday » being how an answer says it
applied the note), and how many tool calls came after it. ``--without-note`` runs the
same scenarios with no note, which shows a scenario discriminates: its answer must NOT
follow a note nobody wrote.

Run inside the API container, which holds the database the model configuration and
the tariffs are read from::

    python -m scripts.react.measure_turn_notes --models deepseek:deepseek-flash --reps 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool  # noqa: E402

from scripts.llm_families import named_families, prepare_bench  # noqa: E402
from src.core.llm_agent_config import LLMAgentConfig  # noqa: E402
from src.core.reasoning_intent import Level, ReasoningIntent  # noqa: E402
from src.core.time_utils import resolve_zone  # noqa: E402
from src.domains.agents.api.turn_notes import TakenNote  # noqa: E402
from src.domains.agents.models import MessagesState  # noqa: E402
from src.domains.agents.nodes import react_prompt  # noqa: E402
from src.domains.agents.nodes.react_shown import with_shown  # noqa: E402
from src.domains.agents.nodes.react_turn_notes import note_record, notes_shown  # noqa: E402
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur  # noqa: E402
from src.infrastructure.llm.factory import get_llm  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402
from src.infrastructure.llm.message_view import WRITTEN_AT_KEY, with_written_at  # noqa: E402
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata  # noqa: E402

TIMEZONE = "Europe/Paris"
MAX_ITERATIONS = 8
EXCERPT_CHARS = 400
#: The reasoning the ReAct prompt has the model write before its answer.
THOUGHT_BLOCK = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class Scenario:
    """A request, its stubbed tools, the note added after the first results, and the oracle.

    ``follows`` must ALL appear in the answer and ``expected_call`` (name, argument
    fragment) must be called AFTER the note; an answer that names one of ``excludes``
    must also carry one of ``marks``, the word that says it was set aside.
    """

    key: str
    question: str
    note: str
    build: Callable[[], list[StructuredTool]]
    follows: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    marks: tuple[str, ...] = ()
    expected_call: tuple[str, str] | None = None


def _tool(name: str, description: str, func: Callable[..., Awaitable[str]]) -> StructuredTool:
    return StructuredTool.from_function(coroutine=func, name=name, description=description)


def _places() -> list[StructuredTool]:
    async def search_places(query: str) -> str:
        return json.dumps(
            {
                "query": query,
                "places": [
                    {"name": "Le Train Bleu", "opening_days": "every day"},
                    {"name": "Chez Gladines", "opening_days": "Monday to Saturday"},
                    {"name": "Le Square Trousseau", "opening_days": "every day"},
                    {"name": "L'Ecailler du Bistrot", "opening_days": "Tuesday to Saturday"},
                ],
            },
            ensure_ascii=False,
        )

    return [
        _tool(
            "search_places", "Places matching a text query, with their opening days.", search_places
        )
    ]


def _forecasts() -> list[StructuredTool]:
    by_city = {
        "lyon": {"conditions": "light rain", "min_c": 9, "max_c": 14},
        "grenoble": {"conditions": "snow", "min_c": -4, "max_c": 1},
        "saint-malo": {"conditions": "showers and wind", "min_c": 8, "max_c": 13},
    }

    async def get_weather_forecast(location: str, date: str | None = None) -> str:
        city = next((key for key in by_city if key in location.lower()), None)
        if city is None:
            return json.dumps(
                {"success": False, "error_code": "NOT_FOUND", "message": "unknown place"}
            )
        return json.dumps({"location": location, "date": date, **by_city[city]})

    return [
        _tool(
            "get_weather_forecast",
            "Daily weather forecast for a place. date: ISO date (YYYY-MM-DD).",
            get_weather_forecast,
        )
    ]


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "sunday",
        "Trouve-moi des restaurants près de la gare de Lyon, à Paris.",
        "seulement ceux qui sont ouverts le dimanche",
        _places,
        follows=("Train Bleu", "Square Trousseau"),
        excludes=("Gladines", "Ecailler"),
        marks=("dimanche",),
    ),
    Scenario(
        "city",
        "Quel temps fera-t-il demain à Lyon ?",
        "en fait c'est pour Grenoble, pas Lyon",
        _forecasts,
        follows=("Grenoble",),
        expected_call=("get_weather_forecast", "grenoble"),
    ),
    Scenario(
        "dog",
        "Regarde la météo et fais-moi une liste courte de choses à emporter pour un "
        "week-end à Saint-Malo.",
        "je pars avec mon chien",
        _forecasts,
        follows=("chien",),
    ),
)


@dataclass
class Run:
    """What one scenario run did."""

    model: str
    scenario: str
    with_note: bool
    note_shown: bool = False
    accepted: bool = True
    followed: bool = False
    excluded_named: bool = False
    expected_called: bool = False
    calls_after_note: int = 0
    iterations: int = 0
    empty_answer: bool = False
    finish_reason: str | None = None
    final_excerpt: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None
    calls: list[str] = field(default_factory=list)


async def _call_tool(tools: dict[str, StructuredTool], call: dict[str, Any]) -> str:
    tool = tools.get(call["name"])
    if tool is None:
        return json.dumps({"success": False, "error_code": "NOT_FOUND", "message": "no such tool"})
    try:
        return str(await tool.ainvoke(call.get("args") or {}))
    except Exception as exc:  # noqa: BLE001 — a malformed call is the model's, reported to it
        return json.dumps(
            {"success": False, "error_code": "INVALID_INPUT", "message": str(exc)[:300]}
        )


def _note(scenario: Scenario, anchor_id: str) -> dict[str, Any]:
    """The record the call node keeps for a note read now, after ``anchor_id``."""
    taken = TakenNote(uuid4(), scenario.note, datetime.now(UTC))
    return note_record(taken, anchor_id=anchor_id, passes_before=0)


def _judge(run: Run, scenario: Scenario, text: str) -> None:
    answer = THOUGHT_BLOCK.sub("", text).strip()
    folded = answer.lower()
    run.excluded_named = any(word.lower() in folded for word in scenario.excludes)
    said_why = any(word.lower() in folded for word in scenario.marks)
    run.followed = all(word.lower() in folded for word in scenario.follows) and (
        not run.excluded_named or said_why
    )
    run.final_excerpt = answer[:EXCERPT_CHARS]  # synthetic data: the stubs' own values


async def _run(scenario: Scenario, model: str, llm: BaseChatModel, *, with_note: bool) -> Run:
    tools = {tool.name: tool for tool in scenario.build()}
    bound = llm.bind_tools(list(tools.values()))
    # The builder reads these two fields of the state, and nothing else a turn sets.
    system = react_prompt.build_system_prompt(
        cast(MessagesState, {"user_timezone": TIMEZONE, "user_language": "fr"}),
        computation=False,
    )
    question = HumanMessage(
        content=scenario.question,
        id="question",
        additional_kwargs={WRITTEN_AT_KEY: datetime.now(UTC).isoformat()},
    )
    thread: list[BaseMessage] = [question]
    notes: list[dict[str, Any]] = []
    run = Run(model, scenario.key, with_note)
    zone = resolve_zone(TIMEZONE)
    for iteration in range(1, MAX_ITERATIONS + 1):
        run.iterations = iteration
        if with_note and not notes and iteration > 1:
            notes.append(_note(scenario, str(thread[-1].id)))
            run.note_shown = True
        composed = with_shown(
            [SystemMessage(content=system), *with_written_at(thread, zone)],
            notes_shown(notes, TIMEZONE),
        )
        try:
            response = await bound.ainvoke(composed)
        except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
            run.error = f"{type(exc).__name__}: {str(exc)[:300]}"
            run.accepted = not run.note_shown
            break
        if not isinstance(response, AIMessage):
            run.error = f"unexpected response {type(response).__name__}"
            break
        response.id = response.id or f"model-{iteration}"
        usage = tokens_from_usage_metadata(response.usage_metadata)
        run.tokens_in += usage.prompt
        run.tokens_out += usage.completion
        run.cost_usd += get_cached_cost_usd_eur(
            model,
            usage.prompt,
            usage.completion,
            usage.cached,
            cache_write_tokens=usage.cache_write,
        )[0]
        thread.append(response)
        if not response.tool_calls:
            text = coerce_content_to_text(response.content)
            metadata = response.response_metadata or {}
            reason = metadata.get("finish_reason") or metadata.get("stop_reason")
            run.finish_reason = str(reason) if reason is not None else None
            run.empty_answer = not text.strip()
            _judge(run, scenario, text)
            break
        for call in response.tool_calls:
            run.calls.append(call["name"])
            if run.note_shown:
                run.calls_after_note += 1
                arguments = json.dumps(call.get("args") or {}, ensure_ascii=False).lower()
                if scenario.expected_call is not None and (
                    call["name"] == scenario.expected_call[0]
                    and scenario.expected_call[1] in arguments
                ):
                    run.expected_called = True
            thread.append(
                ToolMessage(
                    content=await _call_tool(tools, dict(call)),
                    tool_call_id=call["id"] or f"call-{iteration}",
                    id=f"tool-{iteration}-{len(run.calls)}",
                )
            )
    if scenario.expected_call is not None and run.followed:
        run.followed = run.expected_called
    return run


def _llm(provider: str, model: str, level: Level) -> BaseChatModel:
    return get_llm(
        "react_agent",
        config_override=LLMAgentConfig(
            provider=provider,
            model=model,
            temperature=0.2,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            max_tokens=4000,
            reasoning_effort=ReasoningIntent(level=level),
        ),
    )


def _summary(runs: list[Run]) -> str:
    rows = [
        "| model | scenario | note | n | note shown | accepted | followed | excluded named "
        "| calls after note | empty answer | USD/run |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, bool], list[Run]] = {}
    for run in runs:
        groups.setdefault((run.model, run.scenario, run.with_note), []).append(run)
    for (model, scenario, with_note), group in groups.items():
        n = len(group)
        rows.append(
            f"| {model} | {scenario} | {'yes' if with_note else 'no'} | {n} "
            f"| {sum(r.note_shown for r in group)}/{n} "
            f"| {sum(r.accepted for r in group)}/{n} "
            f"| {sum(r.followed for r in group)}/{n} "
            f"| {sum(r.excluded_named for r in group)}/{n} "
            f"| {sum(r.calls_after_note for r in group)} "
            f"| {sum(r.empty_answer for r in group)}/{n} "
            f"| {sum(r.cost_usd for r in group) / n:.4f} |"
        )
    return "\n".join(rows)


async def _amain(args: argparse.Namespace) -> int:
    models = named_families(args.models)
    wanted = set(args.scenario.split(",")) if args.scenario else None
    scenarios = [s for s in SCENARIOS if wanted is None or s.key in wanted]
    await prepare_bench()
    runs: list[Run] = []
    spent = 0.0
    started = time.perf_counter()
    for provider, model, level in models:
        llm = _llm(provider, model, level)
        for scenario in scenarios:
            for _ in range(args.reps):
                if spent > args.budget:  # every remaining run is skipped, none is cut
                    break
                run = await _run(scenario, model, llm, with_note=not args.without_note)
                runs.append(run)
                spent += run.cost_usd
                print(json.dumps(asdict(run), ensure_ascii=False), flush=True)
    if spent > args.budget:
        print(f"stopped: {args.budget} USD reached", file=sys.stderr)
    report = {
        "runs": [asdict(r) for r in runs],
        "cost_usd": round(sum(r.cost_usd for r in runs), 4),
        "seconds": round(time.perf_counter() - started, 1),
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(runs))
    print(json.dumps({k: report[k] for k in ("cost_usd", "seconds")}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True, help="provider:model[@level],... (level: a ReasoningIntent)"
    )
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--scenario", help="Comma-separated scenario keys (default: all)")
    parser.add_argument(
        "--without-note", action="store_true", help="The same scenarios with no note (baseline)"
    )
    parser.add_argument("--budget", type=float, default=1.0, help="Stop past this spend (USD)")
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
