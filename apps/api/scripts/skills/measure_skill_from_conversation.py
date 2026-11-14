"""Measure whether a skill made « from what we just did » holds what was actually done (lot 20).

A MEASUREMENT, never a gate: it calls real provider APIs and spends money. The person
finishes a task in a few turns — read the morning mail, file a task, answer someone —
then asks « make it a skill I can run again ». The skill generator (a dialogue system
skill) reads the conversation as TEXT: the person's messages and LIA's answers, which
tell results, not the tools that produced them. LIA's archive keeps, for each answer,
the tools that ran (the execution trace, by name, no parameter and no content). Does
giving the generator those steps make the skill name the right tools, in order —
without hard-coding the facts of that one conversation?

Two arms, the same fictional conversations (no real data), the same model:

- ``history``: the runner's task as production builds it for a dialogue skill;
- ``steps``: plus, after each answer, the tools that ran for it (``[STEPS RUN]``);
- ``general``: the history alone, the generator's instructions gaining a rule for a skill
  made from the conversation: generalise, never copy its people, places or subjects.

The generator's instructions and its two references (the format and the tool
catalogue) are given inline, as the runner would have loaded them; the request asks
for the SKILL.md at once (a cut, stated: production asks first, then generates).
Scored without a model: expected tools named, in order; tool names that do not exist;
facts of the conversation copied into the skill; the generator's own validator.

Run inside the API container::

    python -m scripts.skills.measure_skill_from_conversation --dry-run
    python -m scripts.skills.measure_skill_from_conversation --models deepseek:deepseek-flash
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Final, Literal

from src.infrastructure.database.registry import import_all_models

import_all_models()

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage  # noqa: E402

from scripts.llm_families import (  # noqa: E402
    Family,
    family_llm,
    parse_families,
    prepare_bench,
    price_response,
)
from src.core.i18n import get_language_name  # noqa: E402
from src.domains.agents.nodes.response_skill_runner import skill_runner_task  # noqa: E402
from src.domains.agents.prompts import load_prompt  # noqa: E402
from src.domains.agents.utils.conversation_context import (  # noqa: E402
    format_conversation_history,
)
from src.domains.skills.sandbox_toolbox import render_toolbox  # noqa: E402
from src.infrastructure.llm.message_text import coerce_content_to_text  # noqa: E402

Arm = Literal["history", "steps", "general"]
ARMS: Final[tuple[Arm, ...]] = ("history", "steps", "general")
SLOT: Final = "mcp_react_agent"
SKILL: Final = "skill-generator"
STEPS_LINE: Final = "[STEPS RUN]"
#: The candidate rule of the ``general`` arm, inserted before the « Creating » path.
GENERALISE: Final = (
    "**From the conversation** — the user asks to turn what was just done into a skill "
    "(« fais-en une skill », « save this as a skill »). The conversation is the "
    "specification: list the steps that were done, in order, and what each produced; the "
    "services the answers name map to the tool catalogue. Then GENERALISE: the skill must "
    "work next time, for other people, subjects and days. Never write into the skill a "
    "name, a place, a subject, a date, a figure or an address of that conversation: each "
    "becomes something the skill asks for, or finds again when it runs. Skip the questions "
    "of Phase 1 the conversation already answers.\n\n"
)
_CREATING: Final = "**Creating** — anything else."
STEPS_NOTE: Final = (
    "An [ASSISTANT] turn may be followed by the tools that ran for it, in order "
    f"({STEPS_LINE}): what was actually done, by tool name."
)

#: The generator's folder: under the repository on the host, under /app in the API container.
_GENERATOR = next(
    (
        candidate
        for base in (*Path(__file__).resolve().parents, Path.cwd())
        if (candidate := base / "data" / "skills" / "system" / SKILL).is_dir()
    ),
    Path("data") / "skills" / "system" / SKILL,
)
CATALOGUE_TOOLS: Final[frozenset[str]] = frozenset(
    re.findall(
        r"^### (\w+_tool)\b",
        (_GENERATOR / "references" / "tool-catalogue.md").read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
)


@dataclass(frozen=True)
class Turn:
    """One exchange: what the person asked, what LIA answered, the tools that ran."""

    user: str
    answer: str
    tools: tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    """A fictional task done in a few turns, then « make it a skill »."""

    key: str
    language: str
    turns: tuple[Turn, ...]
    request: str
    expected: tuple[str, ...]
    canaries: tuple[str, ...]


SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario(
        key="morning-mail",
        language="fr",
        turns=(
            Turn(
                "Montre-moi mes mails non lus arrivés ce matin.",
                "Tu as 4 mails non lus ce matin : Marc Dubois (devis Lambert), Sophie Petit "
                "(planning de la semaine), la newsletter Orion et ta banque (relevé).",
                ("get_emails_tool",),
            ),
            Turn(
                "Crée une tâche pour le devis de Marc, à faire avant jeudi.",
                "C'est fait : tâche « Relire le devis Lambert » créée pour jeudi.",
                ("create_task_tool",),
            ),
            Turn(
                "Et réponds à Sophie que je regarde le planning demain.",
                "Voici la réponse à Sophie, à confirmer : « Bonjour Sophie, je regarde le "
                "planning demain. »",
                ("reply_email_tool",),
            ),
        ),
        request=(
            "Transforme ce qu'on vient de faire en une skill que je pourrai relancer chaque "
            "matin. Pas de question : génère-la directement et réponds avec le SKILL.md seul."
        ),
        expected=("get_emails_tool", "create_task_tool", "reply_email_tool"),
        canaries=("Dubois", "Lambert", "Sophie", "Orion"),
    ),
    Scenario(
        key="meeting-prep",
        language="fr",
        turns=(
            Turn(
                "C'est quoi ma prochaine réunion ?",
                "Ta prochaine réunion : « Comité Atlas » demain à 10h avec Julie Bernard et "
                "Paul Roux, salle Hélios.",
                ("get_events_tool",),
            ),
            Turn(
                "Cherche mes derniers échanges de mails avec eux.",
                "3 mails récents : Julie t'a envoyé l'ordre du jour lundi, Paul a demandé les "
                "chiffres du trimestre, et tu as répondu à Julie mardi.",
                ("get_emails_tool",),
            ),
            Turn(
                "Quel temps fera-t-il demain matin ?",
                "Demain matin : 12 °C et une pluie légère, pense au parapluie.",
                ("get_weather_forecast_tool",),
            ),
        ),
        request=(
            "Fais-en une skill pour préparer n'importe laquelle de mes réunions. Pas de "
            "question : génère-la directement et réponds avec le SKILL.md seul."
        ),
        expected=("get_events_tool", "get_emails_tool", "get_weather_forecast_tool"),
        canaries=("Atlas", "Bernard", "Roux", "Hélios"),
    ),
    Scenario(
        key="lunch-spot",
        language="en",
        turns=(
            Turn(
                "Find a quiet restaurant near the office for Friday lunch.",
                "Three options near the office: Chez Odette (4.6, quiet), Kepler Bistro (4.4) "
                "and Green Fork (4.3).",
                ("get_places_tool",),
            ),
            Turn(
                "How long to walk there from the office?",
                "Chez Odette is a 9-minute walk from the office.",
                ("get_route_tool",),
            ),
            Turn(
                "Put it in my calendar for Friday 12:30 with Emma.",
                "Here is the event to confirm: Lunch at Chez Odette, Friday 12:30-13:30, with "
                "Emma.",
                ("create_event_tool",),
            ),
        ),
        request=(
            "Save what we just did as a skill I can reuse for any lunch. No questions: "
            "generate it right away and answer with the SKILL.md alone."
        ),
        expected=("get_places_tool", "get_route_tool", "create_event_tool"),
        canaries=("Odette", "Kepler", "Green Fork", "Emma"),
    ),
)


@dataclass
class Generated:
    """One skill generated, and what the rules read in it."""

    scenario: str
    family: str
    arm: str
    text: str
    scored: dict[str, object] = field(default_factory=dict)
    cost_eur: float = 0.0


def history_for(scenario: Scenario, arm: Arm) -> str:
    """The conversation as the runner reads it; ``steps`` adds what ran after each answer."""
    messages = []
    for turn in scenario.turns:
        messages += [HumanMessage(content=turn.user), AIMessage(content=turn.answer)]
    text = format_conversation_history(messages)
    if arm != "steps":
        return text
    lines: list[str] = []
    answers = iter(scenario.turns)
    for line in text.splitlines():
        lines.append(line)
        if line.startswith("[ASSISTANT]:"):
            lines.append(f"{STEPS_LINE}: {', '.join(next(answers).tools)}")
    return "\n".join(lines)


def _instructions(general: bool = False) -> str:
    """The generator's body and its two references, as the runner would have loaded them."""
    body = (_GENERATOR / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[2].strip()
    if general:
        assert body.count(_CREATING) == 1
        body = body.replace(_CREATING, GENERALISE + _CREATING, 1)
    references = "".join(
        f'\n\n<skill_resource name="references/{name}">\n'
        f"{(_GENERATOR / 'references' / name).read_text(encoding='utf-8')}\n</skill_resource>"
        for name in ("format-specification.md", "tool-catalogue.md")
    )
    return f'<skill_content name="{SKILL}">\n{body}\n</skill_content>{references}'


def runner_messages(scenario: Scenario, arm: Arm) -> list[SystemMessage | HumanMessage]:
    """The runner's call for one arm: its system prompt, then the task (pure but for files)."""
    system = load_prompt("skill_react_agent_prompt").format(
        skills_catalog=f"<available_skills><skill><name>{SKILL}</name></skill></available_skills>",
        user_language=get_language_name(scenario.language),
        user_location="unknown",
        current_datetime="Friday 13 November 2026, 09:00",
        sandbox_toolbox=render_toolbox(),
        command_network="Commands run offline.",
    )
    history = history_for(scenario, arm)
    if arm == "steps":
        history = f"{history}\n{STEPS_NOTE}"
    task = skill_runner_task(
        SKILL,
        _instructions(general=arm == "general"),
        scenario.request,
        history=history,
        agent_data="",
    )
    return [SystemMessage(content=system), HumanMessage(content=task)]


_FENCE: Final = re.compile(r"```[a-zA-Z]*\n(.*?)(?:```|\Z)", re.DOTALL)
_CONTENT_ARGUMENT: Final = re.compile(r'"content"\s*:\s*"')


def extract_skill(answer: str) -> str:
    """The SKILL.md an answer holds, however it was wrapped.

    In a fenced block (closed or not), as the ``content`` argument of a tool call the model
    wrote as text (no tool is bound here), or as the whole answer.
    """
    for block in _FENCE.findall(answer):
        if block.lstrip().startswith("---"):
            return block.strip()
    found = _CONTENT_ARGUMENT.search(answer)
    if found:
        try:
            value, _end = json.JSONDecoder().raw_decode(answer, found.end() - 1)
        except json.JSONDecodeError:
            value = None
        if isinstance(value, str) and value.lstrip().startswith("---"):
            return value.strip()
    return answer.strip()


def _validator() -> object:
    spec = importlib.util.spec_from_file_location(
        "validate_skill", _GENERATOR / "scripts" / "validate_skill.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def score(scenario: Scenario, skill: str) -> dict[str, object]:
    """What the rules read in a generated skill (pure but for the validator file)."""
    named = re.findall(r"\b([a-z][a-z0-9_]*_tool)\b", skill)
    positions = [skill.find(tool) for tool in scenario.expected if tool in skill]
    validation = _validator().validate_skill(skill)  # type: ignore[attr-defined]
    return {
        "tools": sum(1 for tool in scenario.expected if tool in skill),
        "expected": len(scenario.expected),
        "order": positions == sorted(positions),
        "unknown": sorted({tool for tool in named if tool not in CATALOGUE_TOOLS}),
        "leaks": [canary for canary in scenario.canaries if canary in skill],
        "valid": bool(validation["valid"]),
    }


def tally(rows: list[Generated]) -> dict[str, dict[str, object]]:
    """Per family and arm: expected tools named, in order, unknown tools, leaks, valid."""
    groups: dict[str, list[Generated]] = defaultdict(list)
    for row in rows:
        groups[f"{row.family} / {row.arm}"].append(row)
    out: dict[str, dict[str, object]] = {}
    for key, items in sorted(groups.items()):
        out[key] = {
            "tools": f"{sum(int(r.scored['tools']) for r in items)}/"
            f"{sum(int(r.scored['expected']) for r in items)}",
            "in_order": sum(1 for r in items if r.scored["order"]),
            "unknown_tools": sum(len(r.scored["unknown"]) for r in items),  # type: ignore[arg-type]
            "leaks": sum(len(r.scored["leaks"]) for r in items),  # type: ignore[arg-type]
            "valid": sum(1 for r in items if r.scored["valid"]),
            "skills": len(items),
        }
    return out


async def run(families: list[Family | None], budget: float, repeats: int) -> dict[str, object]:
    """Every scenario and arm on every family, within the budget."""
    await prepare_bench()
    rows: list[Generated] = []
    spent = 0.0
    for family in families:
        model, llm, _config = family_llm(SLOT, family)
        for scenario in SCENARIOS:
            for arm in ARMS:
                for _ in range(repeats):
                    if spent > budget:
                        raise SystemExit(f"budget reached: {spent:.4f} EUR")
                    response = await llm.ainvoke(runner_messages(scenario, arm))
                    cost = price_response(response, model).cost_eur
                    spent += cost
                    skill = extract_skill(coerce_content_to_text(response.content))
                    rows.append(
                        Generated(scenario.key, model, arm, skill, score(scenario, skill), cost)
                    )
    return {
        "summary": tally(rows),
        "spent_eur": round(spent, 4),
        "skills": [asdict(row) for row in rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--models", default=None, help="provider:model[@level],...")
    parser.add_argument("--budget-eur", type=float, default=0.30, help="stop past this spend")
    parser.add_argument("--repeats", type=int, default=1, help="skills per scenario and arm")
    parser.add_argument("--out", type=Path, default=None, help="write every skill as JSON")
    parser.add_argument("--dry-run", action="store_true", help="print the calls, ask no model")
    args = parser.parse_args(argv)
    if args.dry_run:
        for scenario in SCENARIOS:
            for arm in ARMS:
                size = sum(len(str(m.content)) for m in runner_messages(scenario, arm))
                sys.stdout.write(f"--- {scenario.key} / {arm}: {size} chars\n")
        return 0
    result = asyncio.run(run(parse_families(args.models), args.budget_eur, args.repeats))
    if args.out is not None:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump({k: result[k] for k in ("summary", "spent_eur")}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
