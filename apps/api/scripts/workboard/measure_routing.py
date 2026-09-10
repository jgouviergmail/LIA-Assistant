"""Measure which tool a real model picks for a sentence about the board.

The deterministic half of this corpus is a unit test
(``tests/unit/domains/agents/workboard/test_routing_corpus.py``): it asks
whether the vocabulary can REACH the board at all, and it runs in CI with no
network. This is the other half — whether a model, offered the catalogue as it
actually ships, picks the right capability for each of the 72 utterances.

It is a MEASUREMENT, never a gate. CI holds no provider key, and a paid call on
a path someone must pass to merge is not a build verdict; a test that skipped
on a missing key would be green and would rot (ADR-155). The number belongs in
the ADR, with its date and its model.

**The oracle is the TOOL selected**, per sentence. Two of the twelve families
are NOT workboard families at all: a provider to-do, a timed notification and a
scheduled routine must go elsewhere, and a measurement that only counted the
happy cases would say nothing about the confusion that actually happens.

Nothing here writes to the database and nothing reads a person's data: the
corpus is a fixture, and the only network call goes to the configured provider.

What it spends is NOT in the ledger: the calls go through the client directly,
outside any tracking context, exactly like the recurrence corpus's script. An
operator runs it on purpose, on demand, and reads the cost from the provider's
own console (measured 2026-09-09: about 48 k input tokens per model, a cent).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CORPUS_PATH = (
    REPO_ROOT / "tests" / "unit" / "domains" / "agents" / "workboard" / "routing_corpus.json"
)

#: What the model is asked. The catalogue lines are built from the SHIPPED
#: manifests, so the measurement exercises the wording that actually reaches a
#: planner — measuring a prompt nobody uses would answer a question nobody
#: asked.
_INSTRUCTIONS = """You choose which capability answers a user's sentence.

Here are the capabilities available:

{catalogue}

Answer with a JSON object holding exactly one key, "tool", whose value is the
name of the capability to use — or null when none of them fits and the request
belongs to another part of the assistant. No prose, no code fence.

The sentence is between the markers.
<<<{utterance}>>>"""


def _catalogue() -> str:
    """The tools as a planner sees them, plus the three neighbours.

    The neighbours are named but not described in detail on purpose: what is
    being measured is whether the WORKBOARD's own descriptions are enough to
    keep a sentence away from them.

    Returns:
        One line per capability.
    """
    from src.domains.agents.workboard.catalogue_manifests import (
        comment_ticket_catalogue_manifest,
        create_ticket_catalogue_manifest,
        delete_ticket_catalogue_manifest,
        get_ticket_catalogue_manifest,
        list_tickets_catalogue_manifest,
        update_ticket_catalogue_manifest,
    )

    lines = [
        f"- {manifest.name}: {manifest.description}"
        for manifest in (
            create_ticket_catalogue_manifest,
            update_ticket_catalogue_manifest,
            comment_ticket_catalogue_manifest,
            list_tickets_catalogue_manifest,
            get_ticket_catalogue_manifest,
            delete_ticket_catalogue_manifest,
        )
    ]
    lines += [
        "- create_task_tool: adds a to-do to the user's own provider account "
        "(Google Tasks and the like).",
        "- create_reminder_tool: sends the user a notification at a given " "date and time.",
        "- create_scheduled_action_tool: runs something on a recurring " "schedule, on its own.",
    ]
    return "\n".join(lines)


async def _ask(llm: Any, utterance: str, catalogue: str) -> str | None:
    """Ask the model which capability answers one sentence.

    Args:
        llm: The configured client.
        utterance: What the person said.
        catalogue: The capability lines.

    Returns:
        The tool it chose, or None when it chose none.
    """
    answer = await llm.ainvoke(_INSTRUCTIONS.format(catalogue=catalogue, utterance=utterance))
    text = getattr(answer, "text", None) or str(answer.content)
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    chosen = json.loads(text).get("tool")
    return str(chosen) if chosen else None


def _verdict(family: dict[str, Any], chosen: str | None) -> str:
    """Did the model land where the corpus says it must?

    A NEGATIVE family passes when the model picks anything that is NOT a
    workboard tool: which of the three neighbours it prefers is that domain's
    own business, and judging it here would measure somebody else's wording.

    Args:
        family: The corpus entry.
        chosen: What the model picked.

    Returns:
        ``exact`` or ``wrong``.
    """
    if family["expect_tool"]:
        return "exact" if chosen == family["expect_tool"] else "wrong"
    return "wrong" if (chosen or "").endswith("_ticket_tool") else "exact"


async def main() -> int:
    """Run the measurement and print what it found.

    Returns:
        Always zero: a provider's accuracy is not a build verdict.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slot", default="planner", help="LLM slot to measure.")
    parser.add_argument("--provider", default=None, help="Override the slot's provider.")
    parser.add_argument("--model", default=None, help="Override the slot's model.")
    parser.add_argument("--max-tokens", type=int, default=500, help="Output cap.")
    parser.add_argument("--reasoning", default="low", help="Reasoning level to request.")
    parser.add_argument(
        "--languages",
        default="fr,en,de,es,it,zh-CN",
        help="Comma-separated language codes to measure.",
    )
    parser.add_argument("--report", type=Path, default=None, help="Write the rows as JSON.")
    args = parser.parse_args()

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    families = corpus["families"]
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]

    # The provider keys and the slot overrides live in the DATABASE and are
    # loaded into a process cache at boot; a script that skips this measures a
    # harness with no key (measured 2026-09-09: 72 calls, 72 « unreadable »,
    # every one a 401 with the placeholder key). This is the boot's own step.
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.database.session import get_db_context

    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)

    from src.infrastructure.llm.factory import get_llm

    # A measurement must NAME its model: a percentage without one says nothing
    # anybody can act on, and a slot's model changes underneath.
    if args.model:
        from src.core.llm_agent_config import LLMAgentConfig
        from src.core.reasoning_intent import ReasoningIntent

        llm = get_llm(
            args.slot,
            config_override=LLMAgentConfig(
                provider=args.provider or "openai",
                model=args.model,
                # A reasoning model refuses any other sampling value, and an
                # EXPLICIT intent is what keeps `top_p` out of the request.
                temperature=1.0,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0,
                max_tokens=args.max_tokens,
                reasoning_effort=ReasoningIntent(level=args.reasoning),
            ),
        )
        measured = f"{args.provider or 'openai'} / {args.model} (reasoning={args.reasoning})"
    else:
        llm = get_llm(args.slot)
        measured = f"slot:{args.slot}"
    print("measuring " + measured)

    catalogue = _catalogue()
    rows: list[dict[str, Any]] = []
    for family in families:
        for language in languages:
            if language not in family["utterances"]:
                continue
            try:
                chosen = await _ask(llm, family["utterances"][language], catalogue)
                verdict = _verdict(family, chosen)
            except Exception as failure:  # noqa: BLE001 — a measurement never stops
                chosen, verdict = f"error: {failure}", "unreadable"
            rows.append(
                {
                    "family": family["name"],
                    "language": language,
                    "chosen": chosen,
                    "expected": family["expect_tool"],
                    "verdict": verdict,
                }
            )
            print(f"  {verdict:10} {language:6} {family['name']}")

    exact = sum(1 for row in rows if row["verdict"] == "exact")
    by_language = Counter((row["language"], row["verdict"]) for row in rows)
    by_family = Counter((row["family"], row["verdict"]) for row in rows)

    print(f"\n=== {exact}/{len(rows)} exact ({exact * 100 // max(len(rows), 1)}%) ===")
    print("\nby language:")
    for language in languages:
        total = sum(count for (code, _), count in by_language.items() if code == language)
        if total:
            ok = by_language[(language, "exact")]
            print(f"  {language:6} {ok:3d}/{total:<3d} {ok * 100 // total:3d}%")
    print("\nfamilies that missed at least once:")
    for family in families:
        missed = by_family[(family["name"], "wrong")] + by_family[(family["name"], "unreadable")]
        if missed:
            print(f"  {family['name']:28} {missed} of {len(languages)}")

    if args.report:
        args.report.write_text(
            json.dumps(
                {
                    "measured_at": datetime.now().isoformat(timespec="seconds"),
                    "measured": measured,
                    "exact": exact,
                    "total": len(rows),
                    "rows": rows,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nreport written to {args.report}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
