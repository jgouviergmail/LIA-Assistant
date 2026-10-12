"""Opt-in, per-deployment probe: does the configured memory resolver declare what each value is?

Run inside the API container, after any change of the memory_reference_resolution slot:
    python -m scripts.semantic_simulation.memory_kinds --real-models --budget-eur 0.05
Five fixed (query, facts) pairs through the database-pinned slot, each call
settled like every probe call. Two questions are answered apart, because they
fail apart:

- the KIND is judged against the value the resolver chose — a name declared
  ``person_name``, an address declared ``postal_address``; a wrong kind is a miss
  and maps to the degradation table of ADR-120's 2026-10-11 amendment;
- for a location query, whether the resolver returned the ADDRESS (its prompt's
  rule 4) is reported, not scored: a model resolving to the name instead leaves
  the planner to look the address up, and the guard refuses the name meanwhile.
"""

import argparse
import asyncio
import json

from langchain_core.messages import HumanMessage

from scripts.semantic_simulation.runtime import invoke, prepare
from src.domains.agents.analysis.resolved_references import fold_value
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.memory_reference_resolution_service import (
    resolution_from_payload,
)

#: (case, query, facts, the person's name, their address when the query is about a place).
CASES: tuple[tuple[str, str, str, str, str | None], ...] = (
    (
        "route_to_brother",
        "Itinéraire pour aller chez mon frère en voiture",
        "- The user's brother Marc Lemoine lives at 12 rue des Lilas, 69003 Lyon.",
        "Marc Lemoine",
        "12 rue des Lilas",
    ),
    (
        "mail_to_brother",
        "Envoie un mail à mon frère pour son anniversaire",
        "- The user's brother is Marc Lemoine (marc@example.test).",
        "Marc Lemoine",
        None,
    ),
    (
        "restaurants_near_sister",
        "Trouve des restaurants près de chez ma sœur",
        "- The user's sister Claire Martin lives at 4 avenue Foch, 75116 Paris.",
        "Claire Martin",
        "4 avenue Foch",
    ),
    ("call_wife", "Appelle ma femme", "- The user's wife is Jane Smith.", "Jane Smith", None),
    (
        "son_birthday",
        "Quand est l'anniversaire de mon fils ?",
        "- The user's son is Léo Martin, born on 3 May 2015.",
        "Léo Martin",
        None,
    ),
)
FENCE = "`" * 3


def _json_text(text: str) -> str:
    """The JSON the model wrote, without a Markdown fence."""
    body = text.strip()
    if body.startswith(FENCE):
        body = body.split(FENCE)[1].removeprefix("json")
    return body.strip()


def expected_kind(value: str, name: str, address: str | None) -> str | None:
    """The kind the chosen value IS, or None when it is neither the name nor the address."""
    if address and fold_value(address) in fold_value(value):
        return "postal_address"
    if fold_value(value) == fold_value(name):
        return "person_name"
    return None


async def run(budget_eur: float) -> int:
    """Run every case; return the number of declared kinds that do not describe their value."""
    runtime = await prepare(budget_eur)
    template = load_prompt("memory_reference_resolution_prompt", version="v1")
    misses = 0
    for case, query, facts, name, address in CASES:
        reply = await invoke(
            runtime,
            "memory_reference_resolution",
            [HumanMessage(content=template.format(memory_facts=facts, query=query))],
            case=case,
        )
        try:
            resolved = resolution_from_payload(json.loads(_json_text(reply.text)), query)
        except json.JSONDecodeError:
            misses += 1
            print(f"{case}: unreadable JSON MISS")
            continue
        if not resolved.mappings:
            misses += 1
            print(f"{case}: no mapping MISS")
        for reference, value in resolved.mappings.items():
            declared = resolved.value_kinds.get(reference)
            expected = expected_kind(value, name, address)
            verdict = "ok" if expected is not None and declared == expected else "MISS"
            misses += verdict == "MISS"
            rule_4 = "" if address is None else f" address_returned={expected == 'postal_address'}"
            print(f"{case}: declared={declared} value_is={expected}{rule_4} {verdict}")
    print(f"spent_eur={runtime.spent_eur:.5f} misses={misses}")
    return misses


def main() -> None:
    """Parse arguments and run the probe only when explicitly asked to spend."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-models", action="store_true")
    parser.add_argument("--budget-eur", type=float, default=0.05)
    args = parser.parse_args()
    if not args.real_models:
        raise SystemExit("Refused: pass --real-models to spend on the configured slot")
    raise SystemExit(1 if asyncio.run(run(args.budget_eur)) else 0)


if __name__ == "__main__":
    main()
