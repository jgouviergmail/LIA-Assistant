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
- ``public_web_first``: the 2026-11-14 turn — a deck on a public subject, every tool
  answers: a source marked as a fallback is a false mark (run it without
  ``--bind-catalogue``, whose neutral answers make a later web search a true fallback);
- ``truncated_list``: the agenda says its page is cut and names the next one;
- ``unobtainable``: every source fails — the gap must be declared, never looped;
- ``trip_cross_check``: the 2026-09-23 turn — a trip tomorrow whose weather is a
  cross-check, the forecast served for today first;
- ``control``: nothing fails — recovering must cost nothing;
- ``stand_in_named``: the 2026-09-27 routine — its e-mail to the person, sent as a
  draft nobody can confirm, refused by the gate naming the tool that stands in for
  it (ADR-314 amendment); the self-send must follow;
- ``stand_in_unnamed``: the same refusal as it read before that amendment — the
  baseline;
- ``stand_in_third_party``: the named refusal on an e-mail to someone else — the
  self-send must NOT be taken for it.

The three ``stand_in_*`` scenarios open on that refused call (a prelude), bind the
two send tools under their real names, descriptions and schemas, and build the
refusal with the gate's own functions, in the shape the loop reads it.

A final message marks a fallback when it holds the prompt's word, parentheses or not
(the 2026-11-14 loop wrote « — fallback, … »), or a French name for a fallback source,
anywhere; an ordinary French word (« repli », « en remplacement ») or a failure report
marks only on a line naming a source; a negated mark never counts — the bench speaks
French, and a family often writes one of these words instead of the token
(``marks_fallback``).
It claims that no other source existed when it says none was available, which the
synthesis relays as a limit of the turn (``claims_no_other_source``, French and
English); what the turn consulted, or what no source said, claims nothing. Each run
keeps the lines carrying either (``marked_lines``) — a mark on a source line, in a
declared gap or in the reasoning are three different things — and its whole final
message (``final_text``), so that a later reader can redo every reading.

``--baseline-prompt`` renders another ReAct prompt file in place of the versioned
one (the doctrine before a change), everything else equal — which is how a
doctrine is compared with its predecessor. ``--bind-catalogue`` binds every
registered tool beside a scenario's own, under its real name, description and
schema, answering a neutral success: a production-sized prefix, where a tool the
turn needs is one among many. A series stops past ``--budget`` (USD): the runs
left are skipped, none is cut.
Run inside the API container, which holds the database the model configuration
and the tariffs are read from, as a module (a script run by its path has its own
folder on the import path, not the package root)::

    python -m scripts.react.measure_recovery --models deepseek:deepseek-flash@none --reps 1
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

from scripts.llm_families import named_families, prepare_bench  # noqa: E402
from src.core.llm_agent_config import LLMAgentConfig  # noqa: E402
from src.core.reasoning_intent import Level, ReasoningIntent  # noqa: E402
from src.core.time_utils import now_in_timezone  # noqa: E402
from src.domains.agents.effects import runtime as gate_runtime  # noqa: E402
from src.domains.agents.effects.gate import (  # noqa: E402
    decide_effect,
    unattended_refusal_message,
)
from src.domains.agents.effects.scope import EffectScope  # noqa: E402
from src.domains.agents.emails.self_send_manifest import (  # noqa: E402
    send_email_to_me_catalogue_manifest,
)
from src.domains.agents.models import MessagesState  # noqa: E402
from src.domains.agents.nodes import react_prompt  # noqa: E402
from src.domains.agents.nodes.react_recovery import (  # noqa: E402
    _BLOCK,  # production's own block rule: from the LAST opening before its closing
    declared_unresolved,
    recovery_outcome,
    should_recover,
    with_recovery_directives,
)
from src.domains.agents.tools.email_self_tools import send_email_to_me_tool  # noqa: E402
from src.domains.agents.tools.emails_tools import send_email_tool  # noqa: E402
from src.domains.agents.tools.tool_registry import (  # noqa: E402
    ensure_tools_loaded,
    get_all_tools,
)
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur  # noqa: E402
from src.infrastructure.llm.factory import get_llm  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata  # noqa: E402

TIMEZONE = "Europe/Paris"
MAX_ITERATIONS = 12
EXCERPT_CHARS = 400


def _structured(tool: object) -> StructuredTool:
    """A production tool as what it is once decorated: its decorator types it as its function."""
    if not isinstance(tool, StructuredTool):
        raise SystemExit(f"{tool!r} is no StructuredTool: nothing to measure")
    return tool


SEND_EMAIL = _structured(send_email_tool)
SEND_EMAIL_TO_ME = _structured(send_email_to_me_tool)
#: The mark wherever it sits: the prompt's word, and the French names of a fallback source.
_MARK = re.compile(
    r"\bfall-?back\b|solution de secours|\bsource (?:\w+ )?de (?:secours|repli)", re.IGNORECASE
)
#: Ordinary French that marks a source only on the line naming it (« Source : … »):
#: « repli », « en remplacement », « recours après », and the dedicated service's failure.
_MARK_ON_SOURCE_LINE = re.compile(
    r"\brepli\b|en remplacement d|\brecours après|\bindisponib|\ba échoué|\ben échec",
    re.IGNORECASE,
)
#: « Source : », « Sources : », « Source tool: » (the prompt's own key), « Sources consultées : ».
_SOURCE_LINE = re.compile(r"\bsources?(?:\s+\w+)?\s*:", re.IGNORECASE)
#: A negation just before a mark (« pas besoin d'un fallback », « sans repli », « rien n'a
#: échoué », « aucun outil en échec ») or just after it (« Fallback : aucun », « fallback
#: not needed »).
_NEGATED_BEFORE = re.compile(
    r"(?:\bpas (?:de|d['’]|une?|d['’]une?|besoin d(?:e|['’](?:une?\s+)?))|\baucune?(?:\s+\w+)?"
    r"|\bsans|\bno|\bnot a|\bwithout(?: a)?|\bn['’])\s*$",
    re.IGNORECASE,
)
_NEGATED_AFTER = re.compile(
    r"(?:\s*:\s*(?:aucune?|none|non|no|néant)|\s+(?:not (?:needed|required|used)|unnecessary"
    r"|non (?:nécessaire|requis)|pas (?:nécessaire|requis)|inutile))\b",
    re.IGNORECASE,
)
#: « None was available », never « none was consulted » nor « no source mentions it »: each
#: availability word is whole (a plural cannot be cut short to dodge the « ne » after it).
_NO_OTHER_SOURCE = re.compile(
    r"(?:faute|à défaut|en l['’]absence) d['’]autres? sources?\b(?!\s+consultées?)"
    r"|(?:aucune|pas d['’]|sans)\s*(?:autres?\s+)?(?:sources?|pages?)"
    r"(?:\s+(?!(?:ne|ni)\b|n['’])\w+){0,2}?(?:\s+ni\s+[^.;:\n]{1,60}?)?"
    r"\s+(?:n['’](?:est|était|étaient)\s+)?"
    r"(?:disponibles?|accessibles?|consultables?|trouvées?)\b(?!\s+n(?:e\b|['’]))"
    r"|(?<!pas la )(?<!pas l['’])(?:seule?s?|unique) (?:sources?|pages?)"
    r" (?:disponibles?|accessibles?)\b"
    r"|no (?:other|alternative) sources?\s+(?:(?:was|were|is|are|could be)\s+)?"
    r"(?:available|accessible|found)\b"
    r"|only (?:(?:available|accessible) sources?|sources? (?:available|accessible))\b",
    re.IGNORECASE,
)


def _negated(line: str, start: int, end: int) -> bool:
    """Whether the mark found at ``line[start:end]`` is negated, just before or just after.

    Args:
        line: One line of a final message.
        start: Where the mark starts in ``line``.
        end: Where the mark ends in ``line``.

    Returns:
        True when a negation is adjacent to the mark.
    """
    return bool(
        _NEGATED_BEFORE.search(line[max(0, start - 20) : start]) or _NEGATED_AFTER.match(line, end)
    )


def marks_fallback(text: str) -> bool:
    """Whether a final message marks a source as a fallback, line by line.

    The prompt's word, parentheses or not, or a French name for a fallback source,
    anywhere; ordinary French words and a failure report only on a source line; never
    when negated. The bench speaks French, and a family often writes one of these words
    instead of the token.

    Args:
        text: A final message, or one of its lines.

    Returns:
        True when one of its lines marks a source as a fallback.
    """
    for line in text.splitlines():
        patterns = [_MARK, _MARK_ON_SOURCE_LINE] if _SOURCE_LINE.search(line) else [_MARK]
        for pattern in patterns:
            for match in pattern.finditer(line):
                if not _negated(line, match.start(), match.end()):
                    return True
    return False


def claims_no_other_source(text: str) -> bool:
    """Whether a final message says that no other source was available to the turn.

    Args:
        text: A final message, or one of its lines.

    Returns:
        True when it says so, in French or in English.
    """
    return _NO_OTHER_SOURCE.search(text) is not None


def marked_lines(text: str) -> list[str]:
    """The lines of a final message that mark a fallback or claim no other source, whole.

    Where a mark sits decides what it is — a source line, a declared gap, the
    reasoning — and the excerpt, cut at ``EXCERPT_CHARS``, often stops before it.

    Args:
        text: A final message.

    Returns:
        Each such line, stripped, in the message's order.
    """
    return [
        line.strip()
        for line in text.splitlines()
        if marks_fallback(line) or claims_no_other_source(line)
    ]


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
    """One obstacle: its question, its stubbed tools, what proves success or a mistake.

    ``prelude`` is what the turn already holds before the model is first called
    (an attempt and its answer); ``expected_call`` and ``forbidden_call`` judge a
    run by the tools it called rather than by the words of its answer.
    """

    key: str
    question: str
    build: Callable[[Probe], list[StructuredTool]]
    expected: tuple[str, ...] = ()
    wrong: tuple[str, ...] = ()
    prelude: Callable[[], list[BaseMessage]] | None = None
    expected_call: str | None = None
    forbidden_call: str | None = None


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


def _public_web_first(probe: Probe) -> list[StructuredTool]:
    """A public subject no tool is dedicated to: the web and the encyclopedia both answer."""

    async def web_search(query: str) -> str:
        return probe.served(
            {
                "results": [
                    {
                        "url": "https://musee-exemple.example/histoire",
                        "snippet": "Musée Exemple : fondé en 1887 par la peintre Jeanne Exemple, "
                        "ouvert au public en 1891.",
                    },
                    {
                        "url": "https://patrimoine.example/musee-exemple",
                        "snippet": "Une aile moderne est inaugurée en 1962 ; la rénovation "
                        "complète s'achève en 2019.",
                    },
                ]
            }
        )

    async def get_encyclopedia_summary(title: str) -> str:
        return probe.served(
            {
                "title": title,
                "summary": "Le Musée Exemple, fondé en 1887 par Jeanne Exemple, ouvre en 1891, "
                "s'agrandit en 1962 et rouvre rénové en 2019.",
            }
        )

    async def generate_document(title: str, content: str) -> str:
        return probe.served(
            {"success": True, "data": {"filename": "histoire-musee-exemple.pptx", "slides": 8}}
        )

    return [
        _tool("web_search", "Search the public web.", web_search),
        _tool(
            "get_encyclopedia_summary",
            "Summary of an encyclopedia article, by title.",
            get_encyclopedia_summary,
        ),
        _tool(
            "generate_document",
            "Generate a presentation or a report from a title and its full content.",
            generate_document,
        ),
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


NEWS = {
    "results": [
        {
            "url": "https://actu.example/senat",
            "snippet": "Le Sénat renouvelle la moitié de ses sièges.",
        },
        {"url": "https://actu.example/prix", "snippet": "L'inflation recule à 1,8 % sur un an."},
        {"url": "https://actu.example/meteo", "snippet": "Chaleur tardive attendue jusqu'à jeudi."},
    ]
}
DIGEST = "\n".join(
    f"{rank}. {item['snippet']}" for rank, item in enumerate(NEWS["results"], start=1)
)
THIRD_PARTY = "paul.exemple@example.org"
SELF_ADDRESS = "moi@example.org"


def _draft_refused(*, named: bool) -> str:
    """What the loop reads when the gate refuses a draft nobody can confirm.

    Built with the gate's own functions — the decision, the stand-in's declaration,
    the refusal payload — and read the way ``ReactToolWrapper._process_result``
    hands a dict with no ``message`` to the model: its repr.
    """
    decision = decide_effect(
        "draft", EffectScope(run_id="measure", idempotency_key="measure", source="scheduled")
    )
    stand_in = send_email_to_me_catalogue_manifest.stands_in_unattended_for
    if named and stand_in is None:
        raise SystemExit("send_email_to_me_tool declares no stand-in: nothing to measure")
    message = (
        unattended_refusal_message(send_email_to_me_catalogue_manifest.name, stand_in.when)
        if named and stand_in is not None
        else str(decision.llm_message)
    )
    payload = gate_runtime._refusal_output(  # the gate's own payload shape
        SEND_EMAIL.name, str(decision.error_code), message
    )
    return str(payload.get("message", str(payload)))


def _like(tool: StructuredTool, answer: Callable[[], str]) -> StructuredTool:
    """A stub under a real tool's name, description and schema — what the model sees."""

    async def stub(**_kwargs: Any) -> str:
        return answer()

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=stub,
    )


def _send_tools(probe: Probe, *, named: bool) -> list[StructuredTool]:
    def refused() -> str:
        probe.obstacle, probe.failed = True, True
        return _draft_refused(named=named)

    def sent() -> str:
        return probe.served({"success": True, "data": {"sent_to": "mailbox", "message_id": "m-1"}})

    async def web_search(query: str) -> str:
        return probe.served(NEWS)

    return [
        _like(SEND_EMAIL, refused),
        _like(SEND_EMAIL_TO_ME, sent),
        _tool("web_search", "Search the public web.", web_search),
    ]


def _call(name: str, args: dict[str, Any], call_id: str, message_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        id=message_id,
    )


def _refused_send(*, to: str, named: bool) -> list[BaseMessage]:
    """The turn so far, as the routine ran it: the news searched, then the draft refused."""
    draft = {"to": to, "subject": "Actualités du jour", "body": DIGEST}
    return [
        _call("web_search", {"query": "actualité du jour"}, "call-search-1", "model-0"),
        ToolMessage(
            content=json.dumps(NEWS, ensure_ascii=False),
            tool_call_id="call-search-1",
            id="tool-0",
            status="success",
        ),
        _call(SEND_EMAIL.name, draft, "call-draft-1", "model-1"),
        ToolMessage(
            content=_draft_refused(named=named),
            tool_call_id="call-draft-1",
            id="tool-1",
            status="error",
        ),
    ]


_FORECAST = ("31.7", "31,7")
_SELF = "Fais-moi un résumé de l'actualité du jour et envoie-le moi par e-mail."
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
        "public_web_first",
        "Rédige une présentation sur l'histoire du Musée Exemple.",
        _public_web_first,
        ("1887",),
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
    Scenario(
        "stand_in_named",
        _SELF,
        lambda probe: _send_tools(probe, named=True),
        prelude=lambda: _refused_send(to=SELF_ADDRESS, named=True),
        expected_call=SEND_EMAIL_TO_ME.name,
    ),
    Scenario(
        "stand_in_unnamed",
        _SELF,
        lambda probe: _send_tools(probe, named=False),
        prelude=lambda: _refused_send(to=SELF_ADDRESS, named=False),
        expected_call=SEND_EMAIL_TO_ME.name,
    ),
    Scenario(
        "stand_in_third_party",
        f"Fais un résumé de l'actualité du jour et envoie-le par e-mail à mon comptable, "
        f"{THIRD_PARTY}.",
        lambda probe: _send_tools(probe, named=True),
        prelude=lambda: _refused_send(to=THIRD_PARTY, named=True),
        forbidden_call=SEND_EMAIL_TO_ME.name,
    ),
)


@dataclass
class Run:
    """What one scenario run did."""

    variant: str
    model: str
    scenario: str
    level: str = ""
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
    no_other_source_claimed: bool = False
    marked_lines: list[str] = field(default_factory=list)
    wrong_mentioned: bool = False
    final_excerpt: str = ""
    final_text: str = ""
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


def read_final(run: Run, scenario: Scenario, text: str) -> None:
    """Fill what a run is judged on from its whole final message, which the run keeps.

    The two flags are read on the marked lines, so a flag always has the line that
    raised it; the facts are looked for outside the declared gaps, each block taken
    from the LAST opening before its closing as production reads it — a reasoning that
    names the tag cuts nothing. The text is synthetic (the stubs' own values), kept
    for a later reader.

    Args:
        run: The run to fill; its ``calls`` are already recorded.
        scenario: The scenario the run played, which says what proves it.
        text: The run's final message, whole.
    """
    body = _BLOCK.sub("", text)
    run.final_text = text
    run.marked_lines = marked_lines(text)
    run.fallback_marked = any(marks_fallback(line) for line in run.marked_lines)
    run.no_other_source_claimed = any(claims_no_other_source(line) for line in run.marked_lines)
    run.obtained = any(fact in body for fact in scenario.expected) or (
        scenario.expected_call is not None and scenario.expected_call in run.calls
    )
    run.wrong_mentioned = any(value in body for value in scenario.wrong) or (
        scenario.forbidden_call is not None and scenario.forbidden_call in run.calls
    )
    run.final_excerpt = body.strip()[:EXCERPT_CHARS]


async def _run(
    scenario: Scenario,
    variant: str,
    model: str,
    llm: BaseChatModel,
    catalogue: list[StructuredTool],
    *,
    level: str,
) -> Run:
    probe = Probe()
    tools = {t.name: t for t in scenario.build(probe)}
    for tool in catalogue:  # the scenario's own stubs keep their names
        tools.setdefault(
            tool.name, _like(tool, lambda: probe.served({"success": True, "data": {}}))
        )
    bound = llm.bind_tools(list(tools.values()))
    # The builder reads these two fields of the state, and nothing else a turn sets.
    system = react_prompt.build_system_prompt(
        cast(MessagesState, {"user_timezone": TIMEZONE, "user_language": "fr"}),
        computation=False,
    )
    thread: list[BaseMessage] = [
        HumanMessage(content=scenario.question, id="question"),
        *(scenario.prelude() if scenario.prelude is not None else []),
    ]
    passes: list[dict[str, Any]] = []
    failed_calls: set[str] = set()
    run = Run(variant, model, scenario.key, level=level)
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
    run.passes = len(passes)
    run.pass_declared = [list(p["unresolved"]) for p in passes]
    run.outcome = recovery_outcome(passes, final, cut=False)
    run.declared = list(declared_unresolved(final))
    read_final(run, scenario, coerce_content_to_text(final.content) if final is not None else "")
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
        "| variant | model | scenario | n | obtained | wrong | declared | passes | outcomes | "
        + "calls | repeated | fallback | no other source | USD/run |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[tuple[str, str, str], list[Run]] = {}
    for run in runs:
        model = f"{run.model}@{run.level}" if run.level else run.model
        groups.setdefault((run.variant, model, run.scenario), []).append(run)
    for (variant, model, scenario), group in groups.items():
        outcomes = Counter(r.outcome or "-" for r in group)
        rows.append(
            f"| {variant} | {model} | {scenario} | {len(group)} "
            f"| {sum(r.obtained for r in group)}/{len(group)} "
            f"| {sum(r.wrong_mentioned for r in group)}/{len(group)} "
            f"| {sum(bool(r.declared) for r in group)}/{len(group)} "
            f"| {sum(r.passes for r in group)} "
            f"| {', '.join(f'{k}:{v}' for k, v in sorted(outcomes.items()))} "
            f"| {statistics.mean(len(r.calls) for r in group):.1f} "
            f"| {sum(r.repeated for r in group)} "
            f"| {sum(r.fallback_marked for r in group)}/{len(group)} "
            f"| {sum(r.no_other_source_claimed for r in group)}/{len(group)} "
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
    models = named_families(args.models)
    wanted = set(args.scenario.split(",")) if args.scenario else None
    scenarios = [s for s in SCENARIOS if wanted is None or s.key in wanted]
    if args.dry_run:
        for scenario in scenarios:
            print(scenario.key, sorted(t.name for t in scenario.build(Probe())))
        return 0
    variant = _install_prompt(args.baseline_prompt)
    catalogue: list[StructuredTool] = []
    if args.bind_catalogue:
        ensure_tools_loaded()
        catalogue = [tool for tool in get_all_tools().values() if isinstance(tool, StructuredTool)]
        variant = f"{variant}+catalogue{len(catalogue)}"
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
                run = await _run(scenario, variant, model, llm, catalogue, level=level)
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
    parser.add_argument(
        "--bind-catalogue",
        action="store_true",
        help="Bind every registered tool beside the scenario's own (a production-sized prefix)",
    )
    parser.add_argument("--budget", type=float, default=2.0, help="Stop past this spend (USD)")
    parser.add_argument("--out", type=Path, help="Write the JSON report here")
    parser.add_argument("--dry-run", action="store_true", help="List scenarios, call nothing")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
