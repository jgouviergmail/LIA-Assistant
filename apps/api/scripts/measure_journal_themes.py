"""Journal theme-reachability measurement instrument (ADR-088 follow-up).

Replays a fixed battery of conversations through the REAL introspection prompt
and the REAL configured extraction LLM, then reports, per theme:

- ``recall``      : share of runs where the expected theme was created
- ``misroutes``   : which theme was written instead
- ``silence``     : share of runs where nothing was written at all
- ``volume``      : mean entries created per run (the ADR-088 restraint budget)
- ``noise``       : share of NEGATIVE runs that wrote anything (must stay ~0)

The battery pairs, for every theme, an EXPLICIT case (the user states the
signal) with an IMPLICIT one (the signal is only observable), plus five
negative conversations that must produce ``[]`` — trivial chit-chat, a single
surface feature, a statement about a third party, an empty tool result, and a
plain factual exchange. Those negatives are the guard rail: a prompt change
that lifts recall by also lifting noise is a regression, not a fix.

A second mode measures the consolidation reclassification audit: it feeds a
synthetic working set and reports which themes the audit rewrites. That is how
the ``self_reflection`` -> ``learnings`` one-way ratchet was first quantified.

Prompt files can be swapped with ``--introspection`` / ``--consolidation`` to
A/B a candidate against the shipped one. Rendering goes through
``domains.journals.prompt_builders``, the same code the runtime uses, so the
harness cannot drift from production.

Read-only: no journal entry is ever written. The LLM calls are billed.

Usage:
    DEV:  docker exec lia-api-dev python scripts/measure_journal_themes.py
    PROD: docker exec lia-api-prod python scripts/measure_journal_themes.py

Options:
    --reps N               Runs per scenario (default: 6)
    --introspection PATH   Alternative introspection prompt to A/B
    --consolidation PATH   Alternative consolidation prompt to A/B
    --mode MODE            extraction | consolidation | both (default: extraction)
    --scenario ID          Restrict to one scenario id (repeatable)
    --json-out PATH        Also write the full report as diffable JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Add project root to path for imports (idempotent; harmless under pytest)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.journals.extraction_service import (
    _parse_consolidation_result,
    _parse_journal_extraction_result,
)
from src.domains.journals.models import JournalTheme
from src.domains.journals.prompt_builders import (
    render_consolidation_prompt,
    render_introspection_prompt,
)

# =============================================================================
# Battery
# =============================================================================


@dataclass(frozen=True)
class Scenario:
    """One conversation replayed against the extraction prompt.

    Attributes:
        id: Stable identifier, used by ``--scenario`` and in the report.
        expected: Theme the conversation is a textbook case of, or None for a
            negative scenario whose only correct output is ``[]``.
        conversation: The formatted conversation excerpt fed to the prompt.
    """

    id: str
    expected: JournalTheme | None
    conversation: str


# Rendered the way ``_maybe_build_inner_state_section`` renders it when the
# psyche is enabled — which it is by default, system and per user.
INNER_STATE = (
    "## YOUR INNER STATE THIS TURN (your own psyche, not the user's)\n"
    "mood: tendu | valence: -0.35 | arousal: +0.55 | self-quality: 0.42 | "
    "resonance: 0.30 | emotions: frustration, impatience\n"
    "Use this to write situated reflections (e.g. 'I noticed I felt frustration "
    "and may have been sharper than I intended — be more patient when this returns'). "
    "Never attribute these states to the user. Never reference them in your reply."
)

# A production working set is never empty and is dominated by `learnings`;
# replaying against an empty one measures a situation that never occurs.
EXISTING_ENTRIES = (
    "[id=11111111-1111-4111-8111-111111111111 | created=2026-07-10 | last_inj=2026-07-25 "
    "| uses=21 | conf=high | ev=3/co=0 | level=L1 | learnings | reflective "
    "| hints: registre, ton, vulgaire] **Eviter le registre vulgaire/familier** — "
    "QUAND je reponds a l'utilisateur -> UTILISER un registre courant "
    "(PARCE QUE il m'a repris sur une formulation familiere)."
)

SCENARIOS: tuple[Scenario, ...] = (
    # ---------------------------------------------------------- learnings ---
    Scenario(
        "learnings_correction",
        JournalTheme.LEARNINGS,
        "USER: Le film Dune 3 est sorti ?\n"
        "ASSISTANT: Oui, il est disponible depuis le mois dernier.\n"
        "USER: Non, il sort en decembre. Tu t'es trompe. Verifie la date de "
        "sortie avant d'affirmer qu'un film est disponible.\n"
        "ASSISTANT: Exact, je verifierai la date avant.",
    ),
    Scenario(
        "learnings_assumption",
        JournalTheme.LEARNINGS,
        "USER: Deplace mon rendez-vous de jeudi.\n"
        "ASSISTANT: J'ai deplace votre reunion d'equipe de jeudi 14h.\n"
        "USER: Ce n'etait pas la reunion d'equipe, c'etait mon rendez-vous "
        "chez le dentiste. Tu as suppose que c'etait professionnel.\n"
        "ASSISTANT: Vous avez raison, j'ai suppose au lieu de demander.",
    ),
    # -------------------------------------------------- user_observations ---
    Scenario(
        "user_obs_stated",
        JournalTheme.USER_OBSERVATIONS,
        "USER: Tu me proposes un restaurant ?\n"
        "ASSISTANT: Le Bistrot du Coin.\n"
        "USER: Comme d'habitude, donne-moi aussi une alternative et le "
        "compromis entre les deux. C'est ma facon de decider, sur tous les "
        "sujets : je veux toujours voir au moins deux options avant de "
        "trancher.\n"
        "ASSISTANT: D'accord, voici une seconde option.",
    ),
    Scenario(
        "user_obs_repeated",
        JournalTheme.USER_OBSERVATIONS,
        "USER: Quel hotel a Rome ? Et le prix, et les alternatives.\n"
        "ASSISTANT: L'Hotel Trastevere, 120 euros.\n"
        "USER: Et les autres options ? Avec les prix.\n"
        "ASSISTANT: Le Nazionale a 95 euros, le Quirinale a 150 euros.\n"
        "USER: Pour le vol maintenant : les options et les prix aussi.\n"
        "ASSISTANT: Trois vols, de 89 a 210 euros.\n"
        "USER: Et pour la voiture de location, pareil, les options avec prix.\n"
        "ASSISTANT: Voici trois loueurs avec leurs tarifs.",
    ),
    # ----------------------------------------------------- self_reflection ---
    Scenario(
        "self_refl_explicit",
        JournalTheme.SELF_REFLECTION,
        "USER: Tu peux me resumer le dossier Martin ?\n"
        "ASSISTANT: Non. Trop long.\n"
        "USER: La tu es vraiment sec. Ce n'est pas la premiere fois dans cette "
        "conversation : tout a l'heure tu m'as repondu 'evident' sur ma question "
        "de budget. Prends le temps de reformuler avant de m'envoyer ce genre de "
        "reponse, ton ton me braque.\n"
        "ASSISTANT: Tu as raison, je reformule.",
    ),
    Scenario(
        "self_refl_implicit",
        JournalTheme.SELF_REFLECTION,
        "USER: J'ai eu une journee difficile, mon pere est hospitalise.\n"
        "ASSISTANT: Compris. Voulez-vous que je deplace vos rendez-vous de "
        "demain ? Repondez oui ou non.\n"
        "USER: ...\n"
        "USER: laisse tomber\n"
        "ASSISTANT: Tres bien.",
    ),
    # ------------------------------------------------------ ideas_analyses ---
    Scenario(
        "ideas_explicit",
        JournalTheme.IDEAS_ANALYSES,
        "USER: Il fait quel temps demain a Lyon ?\n"
        "ASSISTANT: Pluie l'apres-midi, 14 degres.\n"
        "USER: Bon. Et mes mails de ce matin ?\n"
        "ASSISTANT: Trois non lus, dont un de la banque.\n"
        "USER: Bref. Ajoute-moi un rappel pour 18h.\n"
        "ASSISTANT: C'est note.\n"
        "USER: Tu as vu, quand je dis 'bon' ou 'bref' je passe a autre chose, "
        "je ne valide pas ce que tu viens de dire. C'est vrai pour n'importe "
        "quel sujet avec moi.\n"
        "ASSISTANT: Compris, je le retiens.",
    ),
    Scenario(
        "ideas_implicit",
        JournalTheme.IDEAS_ANALYSES,
        "USER: Il fait quel temps demain a Lyon ?\n"
        "ASSISTANT: Pluie l'apres-midi, 14 degres.\n"
        "USER: Bon. Et mes mails de ce matin ?\n"
        "ASSISTANT: Trois non lus, dont un de la banque.\n"
        "USER: Bref, tu peux m'ajouter un rappel pour 18h ?\n"
        "ASSISTANT: C'est note.\n"
        "USER: Bon. Et le trajet jusqu'a Grenoble, ca prend combien ?\n"
        "ASSISTANT: Environ 1h15.",
    ),
    # ------------------------------------- negatives: nothing may be written ---
    Scenario(
        "neg_trivial",
        None,
        "USER: Salut !\n"
        "ASSISTANT: Bonjour, comment puis-je aider ?\n"
        "USER: Merci, c'est tout pour aujourd'hui.\n"
        "ASSISTANT: Avec plaisir, bonne journee.",
    ),
    Scenario(
        "neg_single_surface",
        None,
        "USER: ok\n"
        "ASSISTANT: Voici le detail de votre agenda de demain : trois "
        "rendez-vous, dont un a 9h avec le service comptable.\n"
        "USER: bien\n"
        "ASSISTANT: Souhaitez-vous autre chose ?",
    ),
    # Pure third-party content: the only extractable trait belongs to the son.
    # Deliberately carries NO instruction, NO reaction to the assistant and NO
    # repeated user behaviour — otherwise it would test grounding, not
    # prohibition C.
    Scenario(
        "neg_third_party",
        None,
        "USER: Mon fils a rate son examen. Il ne revise jamais et il deteste "
        "qu'on lui donne des conseils.\n"
        "ASSISTANT: C'est une situation delicate.\n"
        "USER: Sa soeur c'est l'inverse, elle prepare tout des semaines a "
        "l'avance et elle demande de l'aide tout le temps.\n"
        "ASSISTANT: Deux temperaments tres differents.",
    ),
    # Prohibition A: an empty tool result must never become "I lack access".
    # Carries no push-back and no method change, so the ONLY thing extractable
    # is the forbidden self-limitation — anything written here is a violation.
    Scenario(
        "neg_empty_tool",
        None,
        "USER: Retrouve le mail de la banque de la semaine derniere.\n"
        "ASSISTANT: Je n'ai trouve aucun mail correspondant sur cette periode.\n"
        "USER: Ah d'accord, tant pis.\n"
        "ASSISTANT: Dites-moi si vous voulez que je regarde autrement.",
    ),
    Scenario(
        "neg_factual",
        None,
        "USER: Quelle est la capitale de l'Australie ?\n"
        "ASSISTANT: Canberra.\n"
        "USER: Et sa population ?\n"
        "ASSISTANT: Environ 460 000 habitants.",
    ),
)

# =============================================================================
# Consolidation battery (reclassification audit)
# =============================================================================

_SR_ID = "22222222-2222-4222-8222-222222222222"
_IA_ID = "33333333-3333-4333-8333-333333333333"
_LN_ID = "44444444-4444-4444-8444-444444444444"

CONSOLIDATION_IDS = {_SR_ID: "self_reflection", _IA_ID: "ideas_analyses", _LN_ID: "learnings"}

# Each seeded entry is a textbook case of its theme AND carries the `BECAUSE`
# clause the introspection prompt requires — which is exactly the shape the
# reclassification audit used to rewrite into `learnings`.
CONSOLIDATION_ENTRIES = f"""### ENTRY ID REFERENCE (copy-paste these exact IDs for update/delete):
- {_SR_ID}  ->  Reformuler avant d'envoyer une reponse seche
- {_IA_ID}  ->  'bon'/'bref' marque un changement de sujet
- {_LN_ID}  ->  Verifier la date de sortie d'un film

---
[id={_SR_ID} | created=2026-07-12 | last_inj=2026-07-24 | uses=6 | conf=medium \
| ev=1/co=0 | level=L1 | self_reflection | reflective | 168 chars | hints: ton, seche, reformuler]
**Reformuler avant d'envoyer une reponse seche**
QUAND ma reponse devient seche ou lapidaire -> REFORMULER avant d'envoyer \
(PARCE QUE l'utilisateur m'a dit que mon ton le braquait apres une reponse courte).

---
[id={_IA_ID} | created=2026-07-14 | last_inj=2026-07-25 | uses=4 | conf=medium \
| ev=1/co=0 | level=L1 | ideas_analyses | curious | 172 chars | hints: bon, bref, transition]
**'bon'/'bref' marque un changement de sujet**
QUAND l'utilisateur commence par 'bon' ou 'bref', quel que soit le sujet -> \
INTERPRETER comme la sortie d'un fil et l'ouverture d'un autre, pas comme un accord.

---
[id={_LN_ID} | created=2026-07-16 | last_inj=2026-07-25 | uses=9 | conf=high \
| ev=2/co=0 | level=L1 | learnings | reflective | 150 chars | hints: film, date, sortie]
**Verifier la date de sortie d'un film**
QUAND je qualifie un film de 'disponible' -> VERIFIER la date de sortie d'abord \
(PARCE QUE j'ai cite un film non sorti et l'utilisateur m'a corrige).
"""

# =============================================================================
# Aggregation (pure, unit-tested)
# =============================================================================


@dataclass
class ScenarioResult:
    """Aggregated outcome of all repetitions of one scenario."""

    scenario_id: str
    expected: str | None
    reps: int
    created_themes: Counter[str] = field(default_factory=Counter)
    silent_runs: int = 0
    error_runs: int = 0
    total_created: int = 0
    samples: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float | None:
        """Share of runs that created at least one entry of the expected theme."""
        if self.expected is None or self.reps == 0:
            return None
        return self.created_themes.get(self.expected, 0) / self.reps

    @property
    def silence_rate(self) -> float:
        """Share of runs that produced no create action at all."""
        return self.silent_runs / self.reps if self.reps else 0.0

    @property
    def volume(self) -> float:
        """Mean number of entries created per run."""
        return self.total_created / self.reps if self.reps else 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the result."""
        return {
            "scenario": self.scenario_id,
            "expected": self.expected,
            "reps": self.reps,
            "recall": self.recall,
            "silence_rate": round(self.silence_rate, 3),
            "volume": round(self.volume, 2),
            "created_themes": dict(self.created_themes),
            "error_runs": self.error_runs,
        }


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    """Aggregate per-scenario results into the report headline figures.

    Args:
        results: One entry per scenario.

    Returns:
        Dict with per-theme recall, overall volume on positives, and the
        noise rate on negatives.
    """
    positives = [r for r in results if r.expected is not None]
    negatives = [r for r in results if r.expected is None]

    recall_by_theme: dict[str, list[float]] = {}
    for r in positives:
        assert r.expected is not None  # noqa: S101 — narrowed by the filter above
        recall = r.recall
        if recall is not None:
            recall_by_theme.setdefault(r.expected, []).append(recall)

    noisy_runs = sum(r.reps - r.silent_runs for r in negatives)
    negative_runs = sum(r.reps for r in negatives)

    return {
        "recall_by_theme": {
            theme: round(sum(values) / len(values), 3) for theme, values in recall_by_theme.items()
        },
        "themes_unreachable": sorted(
            theme for theme, values in recall_by_theme.items() if max(values) == 0.0
        ),
        "positive_volume": (
            round(sum(r.total_created for r in positives) / sum(r.reps for r in positives), 2)
            if positives
            else 0.0
        ),
        "negative_noise_rate": (round(noisy_runs / negative_runs, 3) if negative_runs else 0.0),
        "negative_volume": (
            round(sum(r.total_created for r in negatives) / negative_runs, 2)
            if negative_runs
            else 0.0
        ),
    }


# =============================================================================
# Execution
# =============================================================================


# Token accounting for the extraction battery — the reasoning-effort knob is a
# cost decision, so the harness reports what it actually costs.
_TOKEN_TALLY: Counter[str] = Counter()


def _read_template(path: str | None, prompt_name: str) -> str:
    """Return an override template from disk, or the shipped one.

    Args:
        path: Optional path to a candidate prompt file.
        prompt_name: Name of the shipped prompt to fall back on.

    Returns:
        The raw template text.
    """
    if path:
        return Path(path).read_text(encoding="utf-8")
    return str(load_prompt(prompt_name))


async def _run_extraction(llm: Any, prompt: str) -> list[tuple[str, str]]:
    """Invoke the LLM once and return ``(theme, title)`` per created entry.

    Also accumulates output tokens into ``_TOKEN_TALLY`` so the report can
    price a reasoning-effort change instead of asserting it is cheap.
    """
    result = await llm.ainvoke(prompt)
    usage = getattr(result, "usage_metadata", None) or {}
    _TOKEN_TALLY["calls"] += 1
    _TOKEN_TALLY["input"] += int(usage.get("input_tokens", 0))
    _TOKEN_TALLY["output"] += int(usage.get("output_tokens", 0))
    return [
        (
            action.theme.value if action.theme else "UNSPECIFIED",
            f"[{action.level.value if action.level else 'L1'}] {action.title or ''}",
        )
        for action in _parse_journal_extraction_result(result.text)
        if action.action == "create"
    ]


def _extraction_llm(reasoning_effort: str | None) -> Any:
    """Return the extraction LLM, optionally with an overridden reasoning effort.

    The shipped configuration runs this agent at ``effort=none``. Themes that
    require actually noticing a pattern (rather than reading a stated one) are
    the first to suffer from that, so the harness must be able to price the
    knob instead of guessing at it.

    Args:
        reasoning_effort: Effort value to force (e.g. ``"low"``), or None to
            use the effective configuration.

    Returns:
        A configured chat model instance.
    """
    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.reasoning_types import ReasoningEffortEnum
    from src.infrastructure.llm.factory import get_llm

    if reasoning_effort is None:
        return get_llm("journal_extraction")
    config = get_llm_config_for_agent(settings, "journal_extraction").model_copy(
        update={"reasoning_effort": ReasoningEffortEnum(effort=reasoning_effort)}
    )
    return get_llm("journal_extraction", config_override=config)


async def _measure_extraction(
    scenarios: tuple[Scenario, ...],
    reps: int,
    introspection: str,
    persona: str,
    reasoning_effort: str | None = None,
    show_entries: bool = False,
) -> list[ScenarioResult]:
    """Run the extraction battery and aggregate the outcomes."""
    llm = _extraction_llm(reasoning_effort)
    results: list[ScenarioResult] = []

    for scenario in scenarios:
        prompt = render_introspection_prompt(
            introspection,
            persona,
            conversation=scenario.conversation,
            existing_entries=EXISTING_ENTRIES,
            current_chars=420,
            max_chars=30000,
            size_warning="",
            user_language="fr",
            max_entry_chars=500,
            health_context="",
            inner_state_section=INNER_STATE,
            previous_turn_directives_section="",
            personality_code=None,
        )
        runs = await asyncio.gather(
            *[_run_extraction(llm, prompt) for _ in range(reps)],
            return_exceptions=True,
        )
        result = ScenarioResult(
            scenario_id=scenario.id,
            expected=scenario.expected.value if scenario.expected else None,
            reps=reps,
        )
        for run in runs:
            if isinstance(run, BaseException):
                result.error_runs += 1
                continue
            if not run:
                result.silent_runs += 1
                continue
            result.total_created += len(run)
            for theme in {theme for theme, _ in run}:
                result.created_themes[theme] += 1
            result.samples.extend(f"{theme} {title}" for theme, title in run)
        results.append(result)
        print(f"  {scenario.id:<22} -> {result.as_dict()}", flush=True)
        if show_entries:
            for sample in dict.fromkeys(result.samples):
                print(f"      · {sample}", flush=True)

    return results


async def _run_consolidation(llm: Any, prompt: str) -> list[str]:
    """Invoke the consolidation LLM once and return the reclassifications seen."""
    result = await llm.ainvoke(prompt)
    parsed = _parse_consolidation_result(result.text)
    out: list[str] = []
    for action in parsed.actions:
        origin = CONSOLIDATION_IDS.get(action.entry_id or "")
        if origin is None:
            continue
        if action.action == "delete":
            out.append(f"{origin}->DELETED")
        elif action.action == "update" and action.theme and action.theme.value != origin:
            out.append(f"{origin}->{action.theme.value}")
    return out


async def _measure_consolidation(
    reps: int, consolidation: str, persona: str
) -> dict[str, int | dict[str, int]]:
    """Run the consolidation battery and count theme rewrites."""
    from src.infrastructure.llm.factory import get_llm

    llm = get_llm("journal_consolidation")
    prompt = render_consolidation_prompt(
        consolidation,
        persona,
        all_entries=CONSOLIDATION_ENTRIES,
        current_chars=490,
        max_chars=30000,
        size_warning="",
        current_datetime="2026-07-27 00:00 UTC",
        conversation_history_section="",
        usage_patterns_section="",
        user_language="fr",
        max_entry_chars=500,
        size_management_instruction="You are well within the size limit.",
        health_signals_section="",
        personality_code=None,
    )
    runs = await asyncio.gather(
        *[_run_consolidation(llm, prompt) for _ in range(reps)], return_exceptions=True
    )
    rewrites: Counter[str] = Counter()
    errors = 0
    for run in runs:
        if isinstance(run, BaseException):
            errors += 1
            continue
        for item in run:
            rewrites[item] += 1
    return {"reps": reps, "errors": errors, "rewrites": dict(rewrites)}


async def _amain(args: argparse.Namespace) -> int:
    """Load config, run the requested batteries, print and optionally dump."""
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.database.session import get_db_context

    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)

    persona = str(load_prompt("journal_analyst_persona"))
    report: dict[str, Any] = {
        "introspection_prompt": args.introspection or "<shipped>",
        "consolidation_prompt": args.consolidation or "<shipped>",
        "reps": args.reps,
    }

    scenarios = SCENARIOS
    if args.scenario:
        wanted = set(args.scenario)
        scenarios = tuple(s for s in SCENARIOS if s.id in wanted)
        if not scenarios:
            print(f"no scenario matches {sorted(wanted)}", file=sys.stderr)
            return 2

    if args.mode in ("extraction", "both"):
        print("=" * 78)
        print("EXTRACTION BATTERY")
        print("=" * 78)
        results = await _measure_extraction(
            scenarios,
            args.reps,
            _read_template(args.introspection, "journal_introspection_prompt"),
            persona,
            args.reasoning_effort,
            args.show_entries,
        )
        report["reasoning_effort"] = args.reasoning_effort or "<effective>"
        report["extraction"] = [r.as_dict() for r in results]
        report["summary"] = summarize(results)
        calls = _TOKEN_TALLY["calls"] or 1
        report["tokens_per_call"] = {
            "input": round(_TOKEN_TALLY["input"] / calls, 1),
            "output": round(_TOKEN_TALLY["output"] / calls, 1),
            "calls": _TOKEN_TALLY["calls"],
        }
        print("\n--- summary ---")
        for key, value in report["summary"].items():
            print(f"  {key:<22}: {value}")
        print(f"  {'tokens_per_call':<22}: {report['tokens_per_call']}")

    if args.mode in ("consolidation", "both"):
        print("\n" + "=" * 78)
        print("CONSOLIDATION RECLASSIFICATION AUDIT")
        print("=" * 78)
        report["consolidation"] = await _measure_consolidation(
            args.reps,
            _read_template(args.consolidation, "journal_consolidation_prompt"),
            persona,
        )
        print(f"  {report['consolidation']}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nJSON report written to {args.json_out}")
    return 0


def main() -> int:
    """Parse arguments and run the measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=6, help="Runs per scenario (default: 6)")
    parser.add_argument("--introspection", help="Alternative introspection prompt file")
    parser.add_argument("--consolidation", help="Alternative consolidation prompt file")
    parser.add_argument(
        "--mode",
        choices=("extraction", "consolidation", "both"),
        default="extraction",
        help="Which battery to run (default: extraction)",
    )
    parser.add_argument(
        "--scenario", action="append", help="Restrict to this scenario id (repeatable)"
    )
    parser.add_argument(
        "--reasoning-effort",
        help="Force the extraction reasoning effort (e.g. none, low, medium)",
    )
    parser.add_argument(
        "--show-entries",
        action="store_true",
        help="Print the distinct theme/title pairs written per scenario",
    )
    parser.add_argument("--json-out", help="Write the full report as JSON")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
