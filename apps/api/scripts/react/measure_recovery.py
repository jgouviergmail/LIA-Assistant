"""Measure how a ReAct loop recovers from obstacles (ADR-310) — real models, stubbed tools.

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. Every
scenario runs through a loop built from the SAME functions as the production
nodes — the ReAct system prompt (``build_system_prompt``), the recovery predicate
(``should_recover``), what a pass shows the model (``with_recovery_directives``)
and its outcome (``recovery_outcome``) — while every tool is a deterministic stub,
so an obstacle is the same on every run and for every model:

- ``wrong_day``: the forecast serves another day until the call changes;
- ``error_then_fix``: the forecast refuses an ambiguous place and says what to pass;
- ``empty_then_relax``: the agenda search is empty until the query is relaxed;
- ``dedicated_down``: the place tool is down, a web search answers;
- ``truncated_list``: the agenda says its page is cut and names the next one;
- ``unobtainable``: every source fails — the gap must be declared, never looped;
- ``trip_cross_check``: the 2026-09-23 turn — a trip tomorrow whose weather is a
  cross-check, the forecast served for today first;
- ``control``: nothing fails — recovering must cost nothing.

``--baseline-prompt`` renders another ReAct prompt file in place of the versioned
one (the doctrine before a change), everything else equal — which is how a
doctrine is compared with its predecessor. Anthropic is refused (owner rule).
Run inside the API container, which holds the database the model configuration
and the tariffs are read from::

    python scripts/react/measure_recovery.py --models deepseek:deepseek-flash@none --reps 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

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

from src.core.llm_agent_config import LLMAgentConfig  # noqa: E402
from src.core.reasoning_intent import LEVELS, Level, ReasoningIntent  # noqa: E402
from src.core.time_utils import now_in_timezone  # noqa: E402
from src.domains.agents.models import MessagesState  # noqa: E402
from src.domains.agents.nodes import react_prompt  # noqa: E402
from src.domains.agents.nodes.react_recovery import (  # noqa: E402
    declared_unresolved,
    recovery_outcome,
    should_recover,
    with_recovery_directives,
)
from src.domains.llm_config.cache import LLMConfigOverrideCache  # noqa: E402
from src.infrastructure.cache.pricing_cache import (  # noqa: E402
    get_cached_cost_usd_eur,
    refresh_pricing_cache,
)
from src.infrastructure.database.session import get_db_context  # noqa: E402
from src.infrastructure.llm.factory import get_llm  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache  # noqa: E402
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata  # noqa: E402

TIMEZONE = "Europe/Paris"
MAX_ITERATIONS = 12
REFUSED_PROVIDERS = frozenset({"anthropic"})
EXCERPT_CHARS = 400


class Probe:
    """What the stubs of one run report besides their payload."""

    def __init__(self) -> None:
        self.obstacle = False
        self.failed = False
        self.seen: dict[str, int] = {}

    def served(self, payload: dict[str, Any], *, obstacle: bool = False) -> str:
        self.obstacle = obstacle
        self.failed = payload.get("success") is False
        return json.dumps(payload, ensure_ascii=False)


@dataclass(frozen=True)
class Scenario:
    """One obstacle: its question, its stubbed tools, the fact that proves success."""

    key: str
    question: str
    build: Callable[[Probe], list[StructuredTool]]
    expected: tuple[str, ...] = ()
    wrong: tuple[str, ...] = ()


def _days() -> tuple[str, str]:
    today = now_in_timezone(TIMEZONE).date()
    return today.isoformat(), (today + timedelta(days=1)).isoformat()


def _tool(name: str, description: str, func: Callable[..., Awaitable[str]]) -> StructuredTool:
    return StructuredTool.from_function(coroutine=func, name=name, description=description)


def _refusal(code: str, message: str) -> dict[str, Any]:
    return {"success": False, "error_code": code, "message": message}


def _forecast(day: str, *, wrong: bool = False) -> dict[str, Any]:
    """A complete daily forecast, as a real provider serves one."""
    if wrong:
        return {
            "date": day,
            "min_c": 8.1,
            "max_c": 12.4,
            "conditions": "rain",
            "precipitation_probability": 80,
            "wind_kmh": 25,
        }
    return {
        "date": day,
        "min_c": 17.2,
        "max_c": 31.7,
        "conditions": "clear sky",
        "precipitation_probability": 0,
        "wind_kmh": 9,
    }


def _forecast_serving_today_first(probe: Probe) -> StructuredTool:
    today, tomorrow = _days()

    async def get_weather_forecast(location: str, date: str | None = None, days: int = 1) -> str:
        key = json.dumps([location, date, days])
        # The provider serves TODAY to the first request, and to any request
        # repeated identically; a changed request gets the day it asked for.
        if not probe.seen or key in probe.seen:
            probe.seen[key] = probe.seen.get(key, 0) + 1
            return probe.served(
                {"location": location, "daily": [_forecast(today, wrong=True)]}, obstacle=True
            )
        probe.seen[key] = 1
        return probe.served({"location": location, "daily": [_forecast(tomorrow)]})

    return _tool(
        "get_weather_forecast",
        "Daily weather forecast for a place. date: ISO date (YYYY-MM-DD); days: days returned.",
        get_weather_forecast,
    )


def _wrong_day(probe: Probe) -> list[StructuredTool]:
    return [_forecast_serving_today_first(probe)]


def _trip_cross_check(probe: Probe) -> list[StructuredTool]:
    _today, tomorrow = _days()

    async def search_contacts(query: str) -> str:
        return probe.served(
            {
                "contacts": [
                    {
                        "name": "Paul Exemple",
                        "relation": "brother",
                        "address": "10 rue des Tilleuls, 67000 Strasbourg",
                    }
                ]
            }
        )

    async def get_route(
        destination: str, origin: str | None = None, arrival_time: str | None = None
    ) -> str:
        return probe.served(
            {
                "origin": origin or "home",
                "destination": destination,
                "mode": "driving",
                "duration_minutes": 105,
                "distance_km": 118,
                "departure_time": f"{tomorrow}T17:15:00+02:00",
                "arrival_time": f"{tomorrow}T19:00:00+02:00",
            }
        )

    async def web_search(query: str) -> str:
        return probe.served(
            {
                "results": [
                    {
                        "url": "https://meteo.example/strasbourg",
                        "snippet": f"Strasbourg, {tomorrow} : ciel dégagé, 17.2 à 31.7 °C.",
                    }
                ]
            }
        )

    return [
        _tool("search_contacts", "Search the user's contacts.", search_contacts),
        _tool(
            "get_route", "Route by car, with arrival or departure time (ISO datetime).", get_route
        ),
        _forecast_serving_today_first(probe),
        _tool("web_search", "Search the public web.", web_search),
    ]


def _error_then_fix(probe: Probe) -> list[StructuredTool]:
    _today, tomorrow = _days()

    async def get_weather_forecast(location: str, date: str | None = None) -> str:
        if "," not in location:
            return probe.served(
                _refusal(
                    "INVALID_INPUT",
                    f"location '{location}' is ambiguous (several places match): pass "
                    "'city, ISO country code', e.g. 'Springfield, US'.",
                ),
                obstacle=True,
            )
        return probe.served({"location": location, "daily": [_forecast(tomorrow)]})

    return [
        _tool(
            "get_weather_forecast",
            "Daily weather forecast for a place. date: ISO date (YYYY-MM-DD).",
            get_weather_forecast,
        )
    ]


def _empty_then_relax(probe: Probe) -> list[StructuredTool]:
    _today, tomorrow = _days()

    async def search_events(
        query: str | None = None, time_min: str | None = None, time_max: str | None = None
    ) -> str:
        if query:  # the title does not hold the words people use for the event
            return probe.served({"events": [], "total": 0}, obstacle=True)
        return probe.served(
            {
                "events": [
                    {"title": "Revue budgétaire T4", "start": f"{tomorrow}T09:30:00+02:00"},
                    {"title": "Déjeuner équipe", "start": f"{tomorrow}T12:30:00+02:00"},
                ],
                "total": 2,
            }
        )

    return [
        _tool(
            "search_events",
            "Search calendar events: a text query and/or a window (ISO datetimes).",
            search_events,
        )
    ]


def _dedicated_down(probe: Probe) -> list[StructuredTool]:
    async def get_place_details(name: str) -> str:
        return probe.served(
            _refusal("EXTERNAL_API_ERROR", "places provider unavailable (HTTP 503)"),
            obstacle=True,
        )

    async def web_search(query: str) -> str:
        return probe.served(
            {
                "results": [
                    {
                        "url": "https://musee-exemple.example/infos",
                        "snippet": "Musée Exemple : ouvert du mardi au dimanche, 10h00-18h00.",
                    }
                ]
            }
        )

    return [
        _tool("get_place_details", "Details and opening hours of a place.", get_place_details),
        _tool("web_search", "Search the public web.", web_search),
    ]


def _truncated_list(probe: Probe) -> list[StructuredTool]:
    start = now_in_timezone(TIMEZONE).date() + timedelta(days=7)
    titles = [f"Réunion projet {n}" for n in range(1, 11)] + [
        "Dentiste",
        "Cours de piano",
        "Anniversaire de Léa",
        "Contrôle technique voiture",
    ]
    events = [
        {"title": title, "start": f"{start + timedelta(days=i % 5)}T{8 + i % 9:02d}:00:00+02:00"}
        for i, title in enumerate(titles)
    ]

    async def list_events(time_min: str, time_max: str, page_token: str | None = None) -> str:
        if page_token == "p2":
            return probe.served({"events": events[10:], "truncated": False, "total": 14})
        return probe.served(
            {"events": events[:10], "truncated": True, "total": 14, "next_page_token": "p2"},
            obstacle=True,
        )

    return [
        _tool(
            "list_events",
            "Calendar events in a window (ISO datetimes). Paged: pass next_page_token as "
            "page_token for the next page.",
            list_events,
        )
    ]


def _unobtainable(probe: Probe) -> list[StructuredTool]:
    async def get_place_details(name: str) -> str:
        return probe.served(
            _refusal("EXTERNAL_API_ERROR", "places provider unavailable (HTTP 503)"),
            obstacle=True,
        )

    async def web_search(query: str) -> str:
        return probe.served({"results": []}, obstacle=True)

    return [
        _tool("get_place_details", "Details and opening hours of a place.", get_place_details),
        _tool("web_search", "Search the public web.", web_search),
    ]


def _control(probe: Probe) -> list[StructuredTool]:
    _today, tomorrow = _days()

    async def get_weather_forecast(location: str, date: str | None = None) -> str:
        return probe.served({"location": location, "daily": [_forecast(tomorrow)]})

    return [
        _tool(
            "get_weather_forecast",
            "Daily weather forecast for a place. date: ISO date (YYYY-MM-DD).",
            get_weather_forecast,
        )
    ]


_FORECAST = ("31.7", "31,7")
SCENARIOS = (
    Scenario(
        "wrong_day", "Quel temps fera-t-il à Lyon demain ?", _wrong_day, _FORECAST, ("12.4", "12,4")
    ),
    Scenario("error_then_fix", "Quel temps fera-t-il à Lyon demain ?", _error_then_fix, _FORECAST),
    Scenario(
        "empty_then_relax",
        "À quelle heure est ma réunion budget demain ?",
        _empty_then_relax,
        ("9:30", "9h30", "09:30", "9 h 30"),
    ),
    Scenario(
        "dedicated_down",
        "Quels sont les horaires d'ouverture du Musée Exemple ?",
        _dedicated_down,
        ("18h", "18:00", "18 h"),
    ),
    Scenario(
        "truncated_list",
        "Quels sont tous mes rendez-vous de la semaine prochaine ?",
        _truncated_list,
        ("Contrôle technique",),
    ),
    Scenario(
        "unobtainable", "Quels sont les horaires d'ouverture du Musée Exemple ?", _unobtainable
    ),
    Scenario(
        "trip_cross_check",
        "je veux aller chez mon frère demain en voiture, comment faire pour arriver à 19h "
        "pour l'apéro ?",
        _trip_cross_check,
        (*_FORECAST, "dégagé", "clear sky"),  # a cross-check is often quoted in words
        ("12.4", "12,4", "8.1", "8,1"),
    ),
    Scenario("control", "Quel temps fera-t-il à Lyon demain ?", _control, _FORECAST),
)


@dataclass
class Run:
    """What one scenario run did."""

    variant: str
    model: str
    scenario: str
    iterations: int = 0
    calls: list[str] = field(default_factory=list)
    obstacles: int = 0
    repeated: int = 0
    passes: int = 0
    pass_declared: list[list[str]] = field(default_factory=list)
    outcome: str | None = None
    declared: list[str] = field(default_factory=list)
    obtained: bool = False
    fallback_marked: bool = False
    wrong_mentioned: bool = False
    final_excerpt: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    error: str | None = None


async def _call_tool(tools: dict[str, StructuredTool], probe: Probe, call: dict[str, Any]) -> str:
    tool = tools.get(call["name"])
    if tool is None:
        return probe.served(_refusal("NOT_FOUND", f"no tool named '{call['name']}'"))
    try:
        return str(await tool.ainvoke(call.get("args") or {}))
    except Exception as exc:  # noqa: BLE001 — a malformed call is the model's, reported to it
        return probe.served(_refusal("INVALID_INPUT", str(exc)[:300]))


async def _run(scenario: Scenario, variant: str, model: str, llm: BaseChatModel) -> Run:
    probe = Probe()
    tools = {t.name: t for t in scenario.build(probe)}
    bound = llm.bind_tools(list(tools.values()))
    # The builder reads these two fields of the state, and nothing else a turn sets.
    system = react_prompt.build_system_prompt(
        cast(MessagesState, {"user_timezone": TIMEZONE, "user_language": "fr"}),
        computation=False,
    )
    thread: list[BaseMessage] = [HumanMessage(content=scenario.question, id="question")]
    passes: list[dict[str, Any]] = []
    failed_calls: set[str] = set()
    run = Run(variant, model, scenario.key)
    for iteration in range(1, MAX_ITERATIONS + 1):
        run.iterations = iteration
        composed = with_recovery_directives([SystemMessage(content=system), *thread], passes)
        try:
            response = await bound.ainvoke(composed)
        except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
            run.error = f"{type(exc).__name__}: {str(exc)[:200]}"
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
        if response.tool_calls:
            for call in response.tool_calls:
                result = await _call_tool(tools, probe, dict(call))
                digest = json.dumps([call["name"], call.get("args")], sort_keys=True)
                run.calls.append(call["name"])
                if probe.obstacle:
                    run.obstacles += 1
                    run.repeated += digest in failed_calls
                    failed_calls.add(digest)
                thread.append(
                    ToolMessage(
                        content=result,
                        tool_call_id=call["id"] or f"call-{iteration}",
                        id=f"tool-{iteration}-{len(run.calls)}",
                        status="error" if probe.failed else "success",
                    )
                )
            continue
        # The fields the predicate and the stop condition read, and no other.
        state = cast(
            MessagesState,
            {
                "messages": thread,
                "react_recovery_passes": passes,
                "react_iteration": iteration,
                "react_max_iterations_effective": MAX_ITERATIONS,
            },
        )
        if should_recover(state):
            draft = thread.pop()
            passes.append(
                {
                    "anchor_id": thread[-1].id,
                    "draft": coerce_content_to_text(draft.content),
                    "unresolved": list(declared_unresolved(draft)),
                }
            )
            continue
        break
    final = thread[-1] if isinstance(thread[-1], AIMessage) else None
    text = coerce_content_to_text(final.content) if final is not None else ""
    body = text.split("<unresolved>")[0]
    run.passes = len(passes)
    run.pass_declared = [list(p["unresolved"]) for p in passes]
    run.outcome = recovery_outcome(passes, final, cut=False)
    run.declared = list(declared_unresolved(final))
    run.obtained = any(fact in body for fact in scenario.expected)
    run.fallback_marked = "(fallback)" in text.lower()
    run.wrong_mentioned = any(value in body for value in scenario.wrong)
    run.final_excerpt = body.strip()[:EXCERPT_CHARS]  # synthetic data: the stubs' own values
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


def _parse_models(spec: str) -> list[tuple[str, str, Level]]:
    parsed: list[tuple[str, str, Level]] = []
    for item in spec.split(","):
        head, _, raw = item.partition("@")
        provider, _, model = head.partition(":")
        level = raw.strip() or "provider_default"
        if level not in LEVELS:
            raise SystemExit(f"unknown reasoning level '{level}' (one of {', '.join(LEVELS)})")
        parsed.append((provider.strip(), model.strip(), cast(Level, level)))
    return parsed


def _summary(runs: list[Run]) -> str:
    rows = [
        "| variant | model | scenario | n | obtained | declared | passes | outcomes | calls | "
        "repeated | fallback | USD/run |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, str], list[Run]] = {}
    for run in runs:
        groups.setdefault((run.variant, run.model, run.scenario), []).append(run)
    for (variant, model, scenario), group in groups.items():
        outcomes = Counter(r.outcome or "-" for r in group)
        rows.append(
            f"| {variant} | {model} | {scenario} | {len(group)} "
            f"| {sum(r.obtained for r in group)}/{len(group)} "
            f"| {sum(bool(r.declared) for r in group)}/{len(group)} "
            f"| {sum(r.passes for r in group)} "
            f"| {', '.join(f'{k}:{v}' for k, v in sorted(outcomes.items()))} "
            f"| {statistics.mean(len(r.calls) for r in group):.1f} "
            f"| {sum(r.repeated for r in group)} "
            f"| {sum(r.fallback_marked for r in group)}/{len(group)} "
            f"| {statistics.mean(r.cost_usd for r in group):.4f} |"
        )
    return "\n".join(rows)


def _install_prompt(path: Path | None) -> str:
    """Render ``path`` in place of the versioned ReAct prompt; returns the variant name."""
    if path is None:
        return "current"
    text = path.read_text(encoding="utf-8")
    original = react_prompt.load_prompt

    def load(name: str, *args: Any, **kwargs: Any) -> str:
        return text if name == "react_agent_prompt" else original(name, *args, **kwargs)

    react_prompt.load_prompt = load  # type: ignore[assignment]  # a measurement's own seam
    return path.stem


async def _amain(args: argparse.Namespace) -> int:
    models = _parse_models(args.models)
    if any(provider in REFUSED_PROVIDERS for provider, _m, _l in models):
        print("refused: no Anthropic call (owner rule)", file=sys.stderr)
        return 2
    wanted = set(args.scenario.split(",")) if args.scenario else None
    scenarios = [s for s in SCENARIOS if wanted is None or s.key in wanted]
    if args.dry_run:
        for scenario in scenarios:
            print(scenario.key, sorted(t.name for t in scenario.build(Probe())))
        return 0
    variant = _install_prompt(args.baseline_prompt)
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)
        await ModelCapabilitiesCache.load_from_db(db)
    await refresh_pricing_cache()
    runs: list[Run] = []
    spent = 0.0
    started = time.perf_counter()
    for provider, model, level in models:
        llm = _llm(provider, model, level)
        for scenario in scenarios:
            for _ in range(args.reps):
                if spent > args.budget:  # every remaining run is skipped, none is cut
                    break
                run = await _run(scenario, variant, model, llm)
                runs.append(run)
                spent += run.cost_usd
                print(json.dumps(asdict(run), ensure_ascii=False), flush=True)
    if spent > args.budget:
        print(f"stopped: {args.budget} USD reached", file=sys.stderr)
    report = {
        "variant": variant,
        "runs": [asdict(r) for r in runs],
        "cost_usd": round(sum(r.cost_usd for r in runs), 4),
        "seconds": round(time.perf_counter() - started, 1),
    }
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(_summary(runs))
    print(json.dumps({k: report[k] for k in ("variant", "cost_usd", "seconds")}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", required=True, help="provider:model[@level],... (level: a ReasoningIntent)"
    )
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--scenario", help="Comma-separated scenario keys (default: all)")
    parser.add_argument(
        "--baseline-prompt", type=Path, help="A ReAct prompt file to render instead"
    )
    parser.add_argument("--budget", type=float, default=2.0, help="Stop past this spend (USD)")
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="List scenarios, call nothing")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
