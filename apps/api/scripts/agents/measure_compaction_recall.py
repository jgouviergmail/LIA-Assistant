"""Measure what a compaction keeps of what was said (lot 16).

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. A
compaction replaces the older part of a discussion by a summary, and nothing measured
what that summary keeps. Fictional discussions (``compaction_recall_corpus``) plant
facts where the compaction summarises: the person's own words, a fact a tool
returned, an identifier, a decision LIA took. The production entry node runs on each,
forced as the replay of a refused turn forces it (lot 15), through the real state
reducer, on the compaction slot the database configures or on the families
``--compaction-models`` names (the slot's settings, only the provider, the model and
the reasoning level replaced, handed where the service asks for its model). Then,
per fact:

- ``visible_before``: the response model's view held it before the compaction (its
  window of turns, tool results excluded, as ``response_node`` reads the history);
- ``held_after``: the view holds it after: the summary and the kept tail, read by
  the fact's rule. Free;
- ``answered``: asked the question with only that view, the response model states the
  fact (``--answer``, paid). The prompt is reduced to the view and one instruction:
  a capability probe, not the full response prompt, a cut stated.

``lost_from_view`` counts what the person could still be answered on before the
compaction and no longer after: the compaction's own loss.

``--models`` names the answering families (``provider:model[@level]``); without it
the instance's response slot answers. The tail each compaction kept is reported too:
``starts_mid_exchange`` counts a tail cut between a request and its answer. Run
inside the API container::

    python -m scripts.agents.measure_compaction_recall --dry-run
    python -m scripts.agents.measure_compaction_recall --answer --budget-eur 1
    python -m scripts.agents.measure_compaction_recall --compaction-models deepseek:deepseek-flash
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final
from unittest.mock import patch

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.callbacks import BaseCallbackHandler, UsageMetadataCallbackHandler  # noqa: E402
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402

from scripts.agents.compaction_recall_corpus import (  # noqa: E402
    DISCUSSIONS,
    KINDS,
    Discussion,
    Fact,
    Kind,
    discussion_messages,
)
from scripts.llm_families import (  # noqa: E402
    Family,
    family_llm,
    parse_families,
    prepare_bench,
    price_response,
)
from src.core.config import settings  # noqa: E402
from src.domains.agents.context.runtime_context import LiaRuntimeContext  # noqa: E402
from src.domains.agents.models import MessagesState, create_initial_state  # noqa: E402
from src.domains.agents.nodes.compaction_node import compaction_node  # noqa: E402
from src.domains.agents.services import compaction_service  # noqa: E402
from src.domains.agents.services.compaction_service import compactable_messages  # noqa: E402
from src.domains.agents.utils.message_filters import filter_for_llm_context  # noqa: E402
from src.domains.agents.utils.message_windowing import (  # noqa: E402
    get_response_windowed_messages,
)
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402
from src.infrastructure.llm.message_view import content_for_model  # noqa: E402

RESPONSE_SLOT: Final = "response"
COMPACTION_SLOT: Final = "compaction"
#: The zone every discussion is read in: away from UTC, as a person's clock is.
ZONE: Final = "Europe/Paris"
UNKNOWN: Final = "UNKNOWN"
#: The one instruction the answering model reads besides the view.
INSTRUCTION: Final = (
    "You are given a conversation between a person and their assistant, LIA, possibly "
    "beginning with a summary of its older part. Answer the question with what the "
    f"conversation states, in one short sentence. If it does not state it, answer {UNKNOWN}."
)


@dataclass(frozen=True)
class Row:
    """One fact, where it stood before and after the compaction, and what was answered.

    ``held_after`` is None when nothing was compacted (a dry run); ``summarised`` says
    whether the compaction replaced the fact's exchange or kept it in its tail.
    """

    discussion: str
    fact: str
    kind: Kind
    visible_before: bool
    held_after: bool | None
    answered: bool | None
    summarised: bool = True


def response_view(messages: list[BaseMessage]) -> list[BaseMessage]:
    """The history as the response model reads it: its window of turns, filtered."""
    return filter_for_llm_context(get_response_windowed_messages(messages))


def holds(fact: Fact, messages: list[BaseMessage]) -> bool:
    """Whether the response model's view of these messages still states the fact."""
    text = "\n".join(content_for_model(message) for message in response_view(messages))
    return re.search(fact.pattern, text) is not None


def answered(fact: Fact, answer: str) -> bool:
    """An answer counts when it states the fact without declaring it unknown."""
    return UNKNOWN not in answer and re.search(fact.pattern, answer) is not None


def starts_mid_exchange(messages: list[BaseMessage]) -> bool:
    """Whether what the compaction kept begins inside an exchange, not at a person's message.

    Measured on the baseline (2026-11-15): a tail cut after the person's message and
    before LIA's answer reads to the summarizer as a request left unanswered, and to the
    response model as an answer without its question.
    """
    kept = [message for message in messages if not isinstance(message, SystemMessage)]
    return bool(kept) and not isinstance(kept[0], HumanMessage)


def summarised_exchanges(discussion: Discussion) -> frozenset[str]:
    """The exchanges whose messages the production compaction summarises.

    Read through the rule the compaction itself applies, so a change of the kept tail
    changes what this bench measures, never silently.
    """
    summarised = {
        str(message.id)
        for message in compactable_messages(
            discussion_messages(discussion), settings.compaction_preserve_recent_messages
        )
    }
    return frozenset(
        exchange.key
        for exchange in discussion.exchanges
        if f"{discussion.key}-{exchange.key}-person" in summarised
    )


async def compacted(
    discussion: Discussion, *, callbacks: Sequence[BaseCallbackHandler]
) -> list[BaseMessage]:
    """The discussion's messages after the production entry node compacted it.

    A one-node graph over the real state and reducer; the run's context forces the
    compaction as the replay of a refused turn does.
    """
    graph = StateGraph(MessagesState, context_schema=LiaRuntimeContext)
    graph.add_node("compaction", compaction_node)
    graph.add_edge(START, "compaction")
    graph.add_edge("compaction", END)
    app = graph.compile(checkpointer=InMemorySaver())
    user = uuid.UUID(int=16)
    state = create_initial_state(
        user,
        "bench",
        f"bench-{discussion.key}",
        user_timezone=ZONE,
        user_language=discussion.language,
    )
    state["messages"] = discussion_messages(discussion)
    context = LiaRuntimeContext(
        user_id=user,
        thread_id=discussion.key,
        conversation_id=discussion.key,
        language=discussion.language,
        compaction_forced=True,
    )
    final = await app.ainvoke(
        state,
        {"configurable": {"thread_id": discussion.key}, "callbacks": list(callbacks)},
        context=context,
    )
    return list(final["messages"])


def _view_text(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for message in response_view(messages):
        role = (
            "Summary"
            if isinstance(message, SystemMessage)
            else "Person" if isinstance(message, HumanMessage) else "Assistant"
        )
        lines.append(f"{role}: {content_for_model(message)}")
    return "\n\n".join(lines)


def tally(rows: list[Row]) -> dict[str, dict[str, int]]:
    """Exact counts per kind of fact."""
    result: dict[str, dict[str, int]] = {}
    for kind in KINDS:
        of_kind = [row for row in rows if row.kind == kind]
        asked = [row for row in of_kind if row.answered is not None]
        result[kind] = {
            "facts": len(of_kind),
            "held_after": sum(row.held_after is True for row in of_kind),
            "lost_from_view": sum(
                row.visible_before and row.held_after is False for row in of_kind
            ),
            "answered": sum(bool(row.answered) for row in asked),
            "asked": len(asked),
        }
    return result


def _usage_cost_eur(handler: UsageMetadataCallbackHandler) -> float:
    total = 0.0
    for model, usage in handler.usage_metadata.items():
        cached = int((usage.get("input_token_details") or {}).get("cache_read") or 0)
        _usd, eur = get_cached_cost_usd_eur(
            model, int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), cached
        )
        total += eur
    return total


async def _answer(llm: Any, model: str, view: str, fact: Fact) -> tuple[str, float]:
    response = await llm.ainvoke(
        [
            SystemMessage(INSTRUCTION),
            HumanMessage(f"<conversation>\n{view}\n</conversation>\n\nQuestion: {fact.question}"),
        ]
    )
    return coerce_content_to_text(response.content), price_response(response, model).cost_eur


@contextmanager
def compaction_family(family: Family | None) -> Iterator[str]:
    """Hand the compaction a named family for the duration, or leave the slot as configured.

    Yields:
        The name of the model that compacts.
    """
    name, llm, _config = family_llm(COMPACTION_SLOT, family)
    if family is None:
        yield name
        return
    with patch.object(compaction_service, "get_llm", lambda slot, **_kwargs: llm):
        yield name


async def _compact_all(
    family: Family | None, budget_eur: float, spent: float
) -> tuple[str, dict[str, list[BaseMessage]], float]:
    views: dict[str, list[BaseMessage]] = {}
    with compaction_family(family) as name:
        for discussion in DISCUSSIONS:
            if spent >= budget_eur:
                print(f"budget reached before {discussion.key}: {spent:.4f} EUR", file=sys.stderr)
                break
            usage = UsageMetadataCallbackHandler()
            views[discussion.key] = await compacted(discussion, callbacks=[usage])
            spent += _usage_cost_eur(usage)
    return name, views, spent


async def run(
    compaction_families: list[Family | None],
    answer_families: list[Family | None],
    *,
    answer: bool,
    budget_eur: float,
    dry_run: bool,
) -> dict[str, object]:
    """Compact every discussion with each family, read every fact, answer when asked to."""
    if not dry_run:
        await prepare_bench()
    spent = 0.0
    runs: dict[str, object] = {}
    for compaction in compaction_families if not dry_run else [None]:
        views: dict[str, list[BaseMessage]] = {}
        name = "dry-run"
        if not dry_run:
            name, views, spent = await _compact_all(compaction, budget_eur, spent)
        families: dict[str, object] = {}
        answers: dict[str, str] = {}
        for family in answer_families:
            model, llm, _config = (
                family_llm(RESPONSE_SLOT, family) if answer else ("no-answer", None, None)
            )
            rows: list[Row] = []
            for discussion in DISCUSSIONS:
                after = views.get(discussion.key)
                view = _view_text(after) if after is not None else ""
                summarised = summarised_exchanges(discussion)
                for fact in discussion.facts:
                    said: bool | None = None
                    if answer and after is not None and spent < budget_eur:
                        text, cost = await _answer(llm, model, view, fact)
                        spent += cost
                        said = answered(fact, text)
                        # The corpus is fictional: what was answered is kept for diagnosis.
                        answers[f"{model}/{discussion.key}/{fact.key}"] = text
                    rows.append(
                        Row(
                            discussion.key,
                            fact.key,
                            fact.kind,
                            visible_before=holds(fact, discussion_messages(discussion)),
                            held_after=None if after is None else holds(fact, after),
                            answered=said,
                            summarised=fact.exchange in summarised,
                        )
                    )
            families[model] = {"tally": tally(rows), "rows": [asdict(row) for row in rows]}
        runs[name] = {
            "tails": {
                key: {
                    "kept_messages": sum(not isinstance(m, SystemMessage) for m in messages),
                    "starts_mid_exchange": starts_mid_exchange(messages),
                }
                for key, messages in views.items()
            },
            "families": families,
            "views": {key: _view_text(messages) for key, messages in views.items()},
            "answers": answers,
        }
    return {
        "preserve_recent_messages": settings.compaction_preserve_recent_messages,
        "response_window_turns": settings.response_message_window_size,
        "spent_eur": round(spent, 4),
        "runs": runs,
    }


def _print(report: dict[str, object]) -> None:
    print(
        f"tail kept: {report['preserve_recent_messages']} messages; "
        f"response window: {report['response_window_turns']} turns; "
        f"spent: {report['spent_eur']} EUR"
    )
    runs = report["runs"]
    assert isinstance(runs, dict)
    for compaction, body in runs.items():
        print(f"\n#### compacted by {compaction}")
        for key, tail in body["tails"].items():
            cut = "starts mid-exchange" if tail["starts_mid_exchange"] else "starts on the person"
            print(f"  tail of {key}: {tail['kept_messages']} messages, {cut}")
        for name, family in body["families"].items():
            print(f"  == answered by {name}")
            for kind, counts in family["tally"].items():
                print(
                    f"    {kind:<10} held {counts['held_after']}/{counts['facts']}  "
                    f"lost from view {counts['lost_from_view']}  "
                    f"answered {counts['answered']}/{counts['asked']}"
                )
            for row in family["rows"]:
                flags = (
                    ("summarised " if row["summarised"] else "kept       ")
                    + ("in view " if row["visible_before"] else "        ")
                    + {True: "held ", False: "LOST ", None: "-    "}[row["held_after"]]
                    + {True: "answered", False: "missed", None: ""}[row["answered"]]
                )
                print(f"      {row['discussion']:<12} {row['fact']:<12} {row['kind']:<10} {flags}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--dry-run", action="store_true", help="read the corpus, call no model")
    parser.add_argument("--answer", action="store_true", help="ask every question (paid)")
    parser.add_argument("--models", help="answering families: provider:model[@level],...")
    parser.add_argument(
        "--compaction-models", help="compacting families: provider:model[@level],..."
    )
    parser.add_argument("--budget-eur", type=float, default=1.0)
    parser.add_argument("--out", type=Path, help="write the report as JSON")
    args = parser.parse_args(argv)
    report = asyncio.run(
        run(
            parse_families(args.compaction_models),
            parse_families(args.models),
            answer=args.answer,
            budget_eur=args.budget_eur,
            dry_run=args.dry_run,
        )
    )
    _print(report)
    if args.out:
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
