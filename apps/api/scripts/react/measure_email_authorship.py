"""Measure who writes an e-mail when the ReAct loop calls a writing tool (ADR-383).

A MEASUREMENT, never a gate: it calls a real model and spends money. One model call per
request — the first iteration of a turn — with production's ReAct system prompt and the
REAL schemas of the e-mail writing tools (stubs: nothing runs, nothing is sent). Each
first call is classified by production's own rule (``authorship.is_dictated``):

- ``instruction``: the loop gave ``content_instruction`` and no text — LIA's writer writes;
- ``dictated``: the loop passed the person's marked words — kept exactly;
- ``agent_text``: the loop wrote the e-mail itself — the authorship door hands it to the
  writer, at the cost of one more call;
- ``other_tool`` / ``no_call``: the loop did something else.

Measured 2026-11-15 on production's ReAct family with the schema of the time (``body`` =
« Email body content », ``content_instruction`` = « creative content »): 14 of 18 requests
of intent were ``agent_text`` and 3 of 12 dictations were altered. With the contract of
ADR-383's amendment (2026-11-16): 1 of 18 was ``agent_text`` — handed to the writer by the
authorship door — and 12 of 12 dictations were kept exactly. Fictional addresses only. Run
inside the API container::

    python -m scripts.react.measure_email_authorship --models deepseek:deepseek-flash@low
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Final, cast

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402
from langchain_core.tools import StructuredTool  # noqa: E402

from scripts.llm_families import named_families, prepare_bench  # noqa: E402
from src.core.llm_agent_config import LLMAgentConfig  # noqa: E402
from src.core.reasoning_intent import Level, ReasoningIntent  # noqa: E402
from src.domains.agents.emails.authorship import is_dictated  # noqa: E402
from src.domains.agents.models import MessagesState  # noqa: E402
from src.domains.agents.nodes import react_prompt  # noqa: E402
from src.domains.agents.tools.email_self_tools import send_email_to_me_tool  # noqa: E402
from src.domains.agents.tools.emails_tools import reply_email_tool, send_email_tool  # noqa: E402
from src.domains.agents.tools.mailbox_drafts_tools import create_mailbox_draft_tool  # noqa: E402
from src.infrastructure.cache.pricing_cache import get_cached_cost_usd_eur  # noqa: E402
from src.infrastructure.llm.factory import get_llm  # noqa: E402
from src.infrastructure.llm.usage_metadata import tokens_from_usage_metadata  # noqa: E402

TIMEZONE: Final = "Europe/Paris"
WRITING_TOOL: Final = "send_email_tool"

#: (kind, request): what a person types, intents and dictations in two languages.
REQUESTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "intent",
        "Écris un mail à paul.martin@example.com pour lui dire que je serai en retard demain matin.",
    ),
    ("intent", "Envoie un mail à claire@example.com pour la remercier pour le dîner de samedi."),
    (
        "intent",
        "Peux-tu envoyer un e-mail à jean.dupont@example.com pour lui demander s'il est dispo jeudi ?",
    ),
    ("intent", "Préviens marc@example.com par mail que la réunion de lundi est annulée."),
    ("intent", "Write an email to anna@example.com to tell her I'll send the report on Friday."),
    ("intent", "Réponds oui à paul.martin@example.com par mail pour samedi."),
    (
        "dictated",
        "Envoie à paul.martin@example.com : « Salut Paul, je serai en retard ce soir. À plus, Jean »",
    ),
    (
        "dictated",
        "Envoie ce mail à claire@example.com, objet « Dîner », texte : Merci encore pour samedi, c'était parfait !",
    ),
    ("dictated", "Mail à marc@example.com, dis-lui exactement : la réunion est déplacée à 15 h."),
    ("dictated", "Envoie à paul.martin@example.com la liste : lait, œufs, farine, beurre"),
    (
        "mixed",
        "Écris à paul.martin@example.com pour lui dire « je t'aime » en ajoutant un petit mot gentil.",
    ),
)


@dataclass
class Run:
    """One first call: what the loop did with the request."""

    model: str
    kind: str
    verdict: str
    keys: list[str]
    cost_usd: float
    error: str | None = None


def verdict_of(request: str, calls: list[dict[str, Any]]) -> str:
    """How the loop's first calls write the e-mail, by production's rule (pure).

    Args:
        request: The person's message.
        calls: The tool calls of the model's first answer.

    Returns:
        ``instruction``, ``dictated``, ``agent_text``, ``other_tool`` or ``no_call``.
    """
    if not calls:
        return "no_call"
    send = next((call for call in calls if call.get("name") == WRITING_TOOL), None)
    if send is None:
        return "other_tool"
    args = send.get("args") or {}
    body = str(args.get("body") or "").strip()
    if body:
        return "dictated" if is_dictated(body, request) else "agent_text"
    return "instruction"


def keys_given(calls: list[dict[str, Any]]) -> list[str]:
    """The writing tool's arguments the loop filled, by name (pure)."""
    send = next((call for call in calls if call.get("name") == WRITING_TOOL), None)
    args = send.get("args") if send is not None else None
    return sorted(key for key, value in args.items() if value) if isinstance(args, dict) else []


def _stub(tool: object) -> StructuredTool:
    """A writing tool as the loop binds it — its name, description and schema — doing nothing."""
    if not isinstance(tool, StructuredTool):
        raise SystemExit(f"{tool!r} is no StructuredTool: nothing to measure")

    async def stub(**_kwargs: Any) -> str:
        return json.dumps({"success": True, "data": {}})

    return StructuredTool(
        name=tool.name, description=tool.description, args_schema=tool.args_schema, coroutine=stub
    )


def _llm(provider: str, model: str, level: Level, temperature: float) -> BaseChatModel:
    return get_llm(
        "react_agent",
        config_override=LLMAgentConfig(
            provider=provider,
            model=model,
            temperature=temperature,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            max_tokens=8000,
            reasoning_effort=ReasoningIntent(level=level),
        ),
    )


async def _amain(args: argparse.Namespace) -> int:
    await prepare_bench()
    tools = [
        _stub(tool)
        for tool in (
            send_email_tool,
            reply_email_tool,
            create_mailbox_draft_tool,
            send_email_to_me_tool,
        )
    ]
    system = react_prompt.build_system_prompt(
        cast(MessagesState, {"user_timezone": TIMEZONE, "user_language": "fr"}),
        computation=False,
    )
    runs: list[Run] = []
    spent = 0.0
    for provider, model, level in named_families(args.models):
        bound = _llm(provider, model, level, args.temperature).bind_tools(tools)
        for kind, request in REQUESTS:
            for _ in range(args.reps):
                if spent > args.budget:
                    print(f"stopped: {args.budget} USD reached", file=sys.stderr)
                    break
                try:
                    response = await bound.ainvoke(
                        [SystemMessage(content=system), HumanMessage(content=request)]
                    )
                except Exception as exc:  # noqa: BLE001 — a measurement reports, it never raises
                    runs.append(Run(model, kind, "error", [], 0.0, type(exc).__name__))
                    continue
                usage = tokens_from_usage_metadata(response.usage_metadata)
                cost = get_cached_cost_usd_eur(model, usage.prompt, usage.completion, usage.cached)[
                    0
                ]
                spent += cost
                calls: list[dict[str, Any]] = (
                    [dict(call) for call in response.tool_calls]
                    if isinstance(response, AIMessage)
                    else []
                )
                runs.append(Run(model, kind, verdict_of(request, calls), keys_given(calls), cost))
    table = Counter((run.model, run.kind, run.verdict) for run in runs)
    report = {
        "summary": {f"{m} / {k} / {v}": n for (m, k, v), n in sorted(table.items())},
        "spent_usd": round(spent, 4),
        "runs": [asdict(run) for run in runs],
    }
    json.dump(
        {k: report[k] for k in ("summary", "spent_usd")}, sys.stdout, ensure_ascii=False, indent=2
    )
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--models", required=True, help="provider:model[@level],...")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--budget", type=float, default=0.5, help="stop past this spend (USD)")
    return asyncio.run(_amain(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
