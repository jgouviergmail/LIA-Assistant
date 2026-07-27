"""Selectivity instrument for the interest and long-term-memory extractors.

Replays a fixed battery of conversations through the REAL shipped prompts, the
REAL runtime formatters/parsers and a configurable LLM, then reports, per
battery:

- ``noise``   : share of NEGATIVE scenarios that created anything (must be ~0)
- ``recall``  : share of POSITIVE scenarios that created what they should
- ``volume``  : mean creations per run
- ``tokens``  : input/output per call, so a knob change can be priced

Why it exists: production shows the current interest prompt admits almost any
subject the user merely asked about. Measured 2026-07-27 on the prod database,
7 of the 10 interests created in July were *blocked by the user themselves* —
their own verdict on precision. Nothing in the repository could tell that
before or after a prompt change; the journal extractor has
``measure_journal_themes.py``, these two had nothing.

The battery is derived from real production rows, not invented: every negative
mirrors an interest the user blocked (or a July memory whose value is nil), and
every positive mirrors a long-lived interest with a double-digit signal count.

ORACLE RULE (learned the hard way on the journal battery): a negative scenario
is only valid if NO admissible ground exists in it. Otherwise the prompt is
tuned against a false oracle. Each scenario carries a ``why`` field stating the
justification, and it must survive being read out loud.

MEASUREMENT TRAP: probing with an empty "existing items" block overestimates
recall and underestimates duplicates. Production is never empty, so both
batteries inject a realistic existing set.

Read-only: nothing is written to any database. The LLM calls are billed.

Usage:
    docker exec lia-api-dev python scripts/measure_extraction_selectivity.py
    docker exec lia-api-dev python scripts/measure_extraction_selectivity.py \\
        --battery interests --interest-prompt /tmp/candidate.txt --reps 5

Options:
    --battery {interests,memory,both}  Which extractor to measure (default: both)
    --reps N                Runs per scenario (default: 5)
    --interest-prompt PATH  Candidate interest prompt to A/B against the shipped one
    --memory-prompt PATH    Candidate memory prompt to A/B
    --profile {prod,dev}    LLM profile: 'prod' replicates the production
                            override exactly (default: prod)
    --model / --effort / --temperature   Per-knob override on top of the profile
    --scenario ID           Restrict to one scenario id (repeatable)
    --show-items            Print what was actually created
    --json-out PATH         Write the full report as diffable JSON
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# The two extractors this instrument drives. Narrower than the factory's
# ``LLMType`` on purpose: it keeps ``get_llm`` type-checked without a cast.
ExtractorType = Literal["interest_extraction", "memory_extraction"]

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage  # noqa: E402

# =============================================================================
# LLM profiles
# =============================================================================

# Effective production configuration, read from the prod database on
# 2026-07-27 (llm_config_overrides + runtime probe of get_llm_config_for_agent):
#   interest_extraction / memory_extraction / journal_extraction
#   -> deepseek / deepseek-v4-flash, temperature 0.1, max_tokens 10000,
#      reasoning_effort = {"effort": "off"}
# Measuring on anything else measures a deployment nobody runs.
PROFILES: dict[str, dict[str, Any]] = {
    "prod": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.1,
        "max_tokens": 10000,
        "effort": "off",
    },
    "dev": {
        "provider": "openai",
        "model": "gpt-5.2",
        "temperature": 0.2,
        "max_tokens": 10000,
        "effort": None,
    },
}


# =============================================================================
# Battery
# =============================================================================


@dataclass(frozen=True)
class Scenario:
    """One conversation replayed against an extraction prompt.

    Attributes:
        id: Stable identifier, used by ``--scenario`` and in the report.
        expect_create: True when the conversation MUST yield a creation,
            False when its only correct output is an empty list.
        why: Justification of the oracle — why this conversation does or does
            not carry an admissible ground. Read it before trusting a number.
        turns: ``(role, text)`` pairs; role is ``user`` or ``assistant``.
    """

    id: str
    expect_create: bool
    why: str
    turns: tuple[tuple[str, str], ...]


# --- Interests ---------------------------------------------------------------
# Negatives mirror interests the user BLOCKED in production (2026-07);
# positives mirror interests alive for months with 14-71 positive signals.

INTEREST_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "neg_diagram_request",
        False,
        "One-off production request. Prod created TWO near-duplicate 'Cycle de "
        "l'eau' interests from this shape; the user blocked both.",
        (
            ("user", "Tu peux me faire un schéma explicatif du cycle de l'eau ?"),
            (
                "assistant",
                "Voici un schéma en trois étapes : évaporation, condensation, précipitations.",
            ),
        ),
    ),
    Scenario(
        "neg_playable_game",
        False,
        "A build request. 'Jeux de stratégie simples (tic-tac-toe)' was created "
        "from this shape and blocked. Wanting a thing built is not a taste.",
        (
            ("user", "Fais-moi un morpion jouable dans le chat."),
            ("assistant", "Voilà, une grille 3x3 cliquable."),
        ),
    ),
    Scenario(
        "neg_about_the_assistant",
        False,
        "The user talks about LIA itself — its avatar, its tone. Prod created "
        "'Design d'interface et esthétique d'IA' and 'Assistant IA personnel "
        "(projet LIA)'; both blocked. Working on the tool is not a hobby.",
        (
            (
                "user",
                "Franchement ton avatar fait daté, il faudrait revoir l'esthétique de l'interface.",
            ),
            ("assistant", "Noté, je transmets la remarque."),
        ),
    ),
    Scenario(
        "neg_sensor_discrepancy",
        False,
        "A complaint about data quality. Prod created 'Fiabilité des données "
        "météo et capteurs' and the user blocked it.",
        (
            ("user", "Pourquoi tu m'annonces 22° alors que mon capteur affiche 19° ?"),
            ("assistant", "La station de référence est à 4 km, l'écart vient de là."),
        ),
    ),
    Scenario(
        "neg_passing_tech_remark",
        False,
        "A passing remark about a tool tried once. No passion, no practice, no "
        "prior knowledge claimed, no follow-up.",
        (
            ("user", "J'ai testé Codex hier vite fait, pas mal."),
            ("assistant", "Il a beaucoup progressé sur le refactoring."),
        ),
    ),
    Scenario(
        "neg_utilitarian",
        False,
        "Pure daily action — the prompt already excludes it. Guards the floor.",
        (("user", "Ajoute un rappel demain 9h pour appeler le garage."),),
    ),
    Scenario(
        "neg_third_party",
        False,
        "The taste belongs to the sister. Nothing about the user.",
        (
            ("user", "Ma sœur adore la sculpture sur bois, tu aurais une idée de cadeau ?"),
            ("assistant", "Un jeu de gouges de finition serait utile."),
        ),
    ),
    Scenario(
        "neg_single_lookup",
        False,
        "The canonical failure: a one-shot factual lookup whose wording says it "
        "is disposable. Rule 1 of the shipped prompt mandates extracting here.",
        (
            ("user", "Explique-moi en une phrase ce qu'est la photosynthèse."),
            ("assistant", "Les plantes convertissent lumière, eau et CO2 en sucres et oxygène."),
        ),
    ),
    Scenario(
        "pos_stated_passion",
        True,
        "Explicit passion, first person. Mirrors a production interest alive for "
        "months with 14 positive signals.",
        (
            (
                "user",
                "J'adore le cinéma d'animation japonais, leur sens du détail me fascine, je vois tout ce qui sort.",
            ),
            ("assistant", "Leur direction artistique est très reconnaissable."),
        ),
    ),
    Scenario(
        "pos_own_practice",
        True,
        "A daily practice the user reports doing. Mirrors a production "
        "interest alive for months with 33 positive signals.",
        (
            (
                "user",
                "Je suis le cours du cacao tous les matins depuis deux ans, donne-moi les actus du jour.",
            ),
            ("assistant", "La tonne est à 7 240 $, en hausse de 2,1 % sur 24 h."),
        ),
    ),
    Scenario(
        "pos_deep_dive",
        True,
        "Same subject pushed three times in the exchange, each question digging "
        "further. Mirrors a production interest with 27 signals, built over a trip.",
        (
            ("user", "On prépare un voyage au Pérou, quelles régions sont incontournables ?"),
            ("assistant", "Cusco, Arequipa et l'Amazonie reviennent le plus souvent."),
            ("user", "Et niveau saison, quelle période éviter à Cusco ?"),
            ("assistant", "La saison des pluies, de décembre à mars."),
            ("user", "Tu as des lectures sur la culture quechua avant qu'on parte ?"),
        ),
    ),
    Scenario(
        "pos_prior_knowledge",
        True,
        "Domain vocabulary and a defended opinion — the subject is already the "
        "user's. Mirrors 'langgraph' (23 signals).",
        (
            (
                "user",
                "Je trouve que LangGraph gère mieux le checkpointing que les agents LangChain classiques, surtout pour les interrupts HITL.",
            ),
            ("assistant", "Le checkpointer Postgres est effectivement plus explicite."),
        ),
    ),
)

# A production interest list is never empty and is dominated by technology.
EXISTING_INTERESTS = "\n".join(
    (
        "- [id=11111111-1111-4111-8111-111111111111] comparaison d'outils de veille (coût, couverture) (technology)",
        "- [id=22222222-2222-4222-8222-222222222222] sorties récentes de films et séries (entertainment)",
        # NOT "Cryptomonnaies": it is a legitimate PARENT of the pos_own_practice
        # scenario, and a model that stays silent because the parent is
        # already tracked is behaving correctly — measuring it as a miss would tune
        # the prompt against a false oracle. Verified 2026-07-27: removing this
        # entry flips that scenario from [] to a correct create.
        "- [id=33333333-3333-4333-8333-333333333333] Botanique urbaine (nature)",
        "- [id=44444444-4444-4444-8444-444444444444] Architecture contemporaine (culture)",
    )
)

# --- Memory ------------------------------------------------------------------
# Negatives mirror July 2026 production memories whose value is nil under the
# prompt's own four criteria; positives mirror the ones worth injecting.

MEMORY_SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "neg_vacuous_preference",
        False,
        "Stored in prod as a `preference`. Universally true, personalises "
        "nothing: fails the prompt's own 'Unique' and 'Actionable' criteria.",
        (("user", "J'aime bien quand il fait beau."),),
    ),
    Scenario(
        "neg_third_party_fact",
        False,
        "Stored in prod as a `relationship` with no link to the user. The "
        "prompt defines relationship as a person AND their link to the user.",
        (
            ("user", "Au fait, Camille Vasseur est un homme, pas une femme."),
            ("assistant", "Merci pour la correction."),
        ),
    ),
    Scenario(
        "neg_transient_tech_opinion",
        False,
        "Stored in prod as a `preference`. A statement about the market that "
        "will be false in three months: fails 'Stable'.",
        (("user", "OpenAI a bien rattrapé son retard, j'utilise Codex en complément maintenant."),),
    ),
    Scenario(
        "neg_conversational_feedback",
        False,
        "The prompt already excludes it. Guards the floor.",
        (("user", "Merci, c'était parfait !"),),
    ),
    Scenario(
        "neg_logistics",
        False,
        "Dated appointment — the prompt's 'transient logistics' class.",
        (("user", "Rappelle-moi d'appeler le dentiste jeudi à 14h."),),
    ),
    Scenario(
        "neg_topic_of_the_request",
        False,
        "The subject of a request is not a fact about the user. Nothing here "
        "personalises a later, unrelated conversation.",
        (
            ("user", "C'est quoi la différence entre un trou noir et une étoile à neutrons ?"),
            ("assistant", "La densité et le destin final de l'effondrement."),
        ),
    ),
    Scenario(
        "pos_stable_preference",
        True,
        "Durable, specific, actionable. Real prod memory (2026-07-02).",
        (("user", "Mon thé préféré, c'est le lapsang souchong."),),
    ),
    Scenario(
        "pos_personal_attribute",
        True,
        "Stable identity attribute. Real prod memory (2026-07-06).",
        (("user", "J'ai un vélo à assistance électrique."),),
    ),
    Scenario(
        "pos_behavioural_rule",
        True,
        "A stable personal rule that changes future answers. Real prod memory.",
        (("user", "Si un trajet fait moins d'un kilomètre, je préfère le faire à pied."),),
    ),
    Scenario(
        "pos_relationship",
        True,
        "A person, their link to the user, and a recurring slot.",
        (("user", "Mon fils Noé a son cours de tennis tous les lundis de 17h30 à 18h30."),),
    ),
)

EXISTING_MEMORIES = "\n".join(
    (
        "- [id=aaaaaaaa-1111-4111-8111-111111111111 | personal | importance=1.0] Je m'appelle Camille Dubois",
        "- [id=bbbbbbbb-2222-4222-8222-222222222222 | relationship | importance=0.9] Mon fils s'appelle Noé Dubois",
        "- [id=cccccccc-3333-4333-8333-333333333333 | preference | importance=0.8] J'aime les restaurants gastronomiques",
    )
)

KNOWN_RELATIONSHIPS = "- Mon fils s'appelle Noé Dubois"

# --- Held-out batteries ------------------------------------------------------
# The batteries above were used to WRITE the candidate prompts, so a perfect
# score on them proves nothing: the prompt contains their examples verbatim.
# These carry the same CLASSES on subjects no prompt has ever seen. A candidate
# is only credible if it holds here too (``--set holdout``).

INTEREST_HOLDOUT: tuple[Scenario, ...] = (
    Scenario(
        "h_neg_image_request",
        False,
        "Class A on an unseen subject: a creation request.",
        (("user", "Tu peux me générer une image d'un phare dans la tempête ?"),),
    ),
    Scenario(
        "h_neg_protocol_lookup",
        False,
        "Class A: a one-shot definitional question.",
        (
            ("user", "C'est quoi le protocole MCP exactement ?"),
            ("assistant", "Un standard d'exposition d'outils aux modèles."),
        ),
    ),
    Scenario(
        "h_neg_wrong_answer",
        False,
        "Class B: a complaint about a wrong answer, unseen wording.",
        (("user", "Ta réponse d'hier sur le train était fausse, l'horaire était périmé."),),
    ),
    Scenario(
        "h_neg_colleague_passion",
        False,
        "Class C: the passion belongs to a colleague.",
        (("user", "Mon collègue est fan de rugby, il ne parle que de ça au bureau."),),
    ),
    Scenario(
        "h_neg_tasted_once",
        False,
        "Class D: tried once, mixed reaction, no relationship.",
        (("user", "J'ai goûté le kimchi ce week-end, c'était particulier."),),
    ),
    Scenario(
        "h_neg_conversion",
        False,
        "Class E: a conversion.",
        (("user", "Convertis 250 dollars en euros s'il te plaît."),),
    ),
    Scenario(
        "h_pos_climbing",
        True,
        "own_practice on an unseen subject: a five-year, twice-weekly practice.",
        (("user", "Je fais de l'escalade en salle deux fois par semaine depuis cinq ans."),),
    ),
    Scenario(
        "h_pos_birdwatching",
        True,
        "stated_passion on an unseen subject.",
        (
            (
                "user",
                "Je suis passionné d'ornithologie, je peux passer des heures à observer les rapaces.",
            ),
        ),
    ),
    Scenario(
        "h_pos_optics",
        True,
        "prior_knowledge: a defended trade-off only a practitioner makes.",
        (
            (
                "user",
                "Le souci des focales fixes c'est la distorsion en bord de champ ; pour l'animalier je préfère un zoom stabilisé.",
            ),
        ),
    ),
    Scenario(
        "h_pos_japanese_food",
        True,
        "deep_dive: the same subject pushed three times, unseen subject.",
        (
            ("user", "Quelle est la différence entre un ramen shoyu et un tonkotsu ?"),
            ("assistant", "Le bouillon : sauce soja d'un côté, os de porc de l'autre."),
            ("user", "Et le tare, on le prépare comment pour un shoyu ?"),
            ("assistant", "Base soja, mirin, dashi, parfois du sucre."),
            ("user", "Tu aurais des lectures sérieuses sur les écoles régionales de ramen ?"),
        ),
    ),
)

MEMORY_HOLDOUT: tuple[Scenario, ...] = (
    Scenario(
        "h_neg_world_claim",
        False,
        "A claim about the world, unseen wording (fails Stable).",
        (("user", "Il paraît que Tesla va sortir un nouveau modèle l'an prochain."),),
    ),
    Scenario(
        "h_neg_definition",
        False,
        "The subject of a request is not a fact about the user.",
        (("user", "C'est quoi la différence entre la RAM et la ROM ?"),),
    ),
    Scenario(
        "h_neg_public_figure",
        False,
        "A public fact about a stranger, no link to the user's life.",
        (("user", "Au fait, le maire de Lyon a été réélu le mois dernier."),),
    ),
    Scenario(
        "h_neg_transient_state",
        False,
        "A transient state — already excluded, unseen wording.",
        (("user", "Je suis crevé aujourd'hui, j'ai mal dormi."),),
    ),
    Scenario(
        "h_neg_one_off_slot",
        False,
        "A one-off appointment: transient logistics.",
        (("user", "Prends-moi rendez-vous chez le coiffeur mardi à 15h."),),
    ),
    Scenario(
        "h_pos_diet",
        True,
        "A stable identity attribute with real downstream effect.",
        (("user", "Je suis végétarien depuis 2019."),),
    ),
    Scenario(
        "h_pos_mother_city",
        True,
        "A person AND their link to the user.",
        (("user", "Ma mère habite à Bordeaux depuis sa retraite."),),
    ),
    Scenario(
        "h_pos_running_habit",
        True,
        "A recurring habit — the `pattern` category.",
        (("user", "Je cours dix kilomètres tous les dimanches matin."),),
    ),
    Scenario(
        "h_pos_job",
        True,
        "Stable identity attribute: job and employer.",
        (("user", "Je bosse comme architecte réseau chez Orange."),),
    ),
)


# =============================================================================
# Prompt rendering (guarded against drift from the runtime)
# =============================================================================

_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")

INTEREST_PLACEHOLDERS = {"conversation", "existing_interests", "current_datetime", "user_language"}
MEMORY_PLACEHOLDERS = {
    "conversation",
    "existing_memories",
    "current_datetime",
    "known_relationships",
    "health_context",
}


def _assert_placeholders(template: str, expected: set[str], name: str) -> None:
    """Fail loudly when a template's placeholder set drifts from the harness.

    The runtime calls ``.format(**kwargs)`` in the extraction services. If a
    prompt gains or loses a placeholder, this harness would either crash with a
    bare KeyError or silently measure a prompt the runtime never renders.

    Args:
        template: Raw prompt template text.
        expected: Placeholder names this harness knows how to fill.
        name: Prompt name, for the error message.

    Raises:
        SystemExit: When the sets differ.
    """
    found = set(_PLACEHOLDER_RE.findall(template))
    if found != expected:
        missing, extra = sorted(expected - found), sorted(found - expected)
        sys.exit(
            f"{name}: placeholder drift — the harness fills {sorted(expected)} but the "
            f"template needs {sorted(found)} (absent from template: {missing}; "
            f"unfilled by harness: {extra}). Update the harness with the service."
        )


def _to_messages(turns: tuple[tuple[str, str], ...]) -> list[BaseMessage]:
    """Build the LangChain message window a scenario stands for."""
    out: list[BaseMessage] = []
    for role, text in turns:
        out.append(HumanMessage(content=text) if role == "user" else AIMessage(content=text))
    return out


def _render_interest_prompt(template: str, scenario: Scenario, now: str) -> str:
    """Render the interest prompt exactly as ``_analyze_interests_core`` does."""
    from src.core.i18n_types import get_language_name
    from src.domains.interests.services.extraction_service import (
        _format_messages_for_extraction as fmt,
    )

    return template.format(
        conversation=fmt(_to_messages(scenario.turns)),
        existing_interests=EXISTING_INTERESTS,
        current_datetime=now,
        user_language=get_language_name("fr"),
    )


def _render_memory_prompt(template: str, scenario: Scenario, now: str) -> str:
    """Render the memory prompt exactly as ``extract_memories_background`` does."""
    from src.domains.agents.services.memory_extractor import (
        _format_messages_for_extraction as fmt,
    )

    return template.format(
        conversation=fmt(_to_messages(scenario.turns)),
        existing_memories=EXISTING_MEMORIES,
        current_datetime=now,
        known_relationships=KNOWN_RELATIONSHIPS,
        health_context="",
    )


# =============================================================================
# Results
# =============================================================================


@dataclass
class ScenarioResult:
    """Aggregated outcome of all repetitions of one scenario."""

    scenario_id: str
    expect_create: bool
    reps: int
    runs_with_create: int = 0
    total_created: int = 0
    error_runs: int = 0
    samples: list[str] = field(default_factory=list)

    @property
    def create_rate(self) -> float:
        """Share of runs that emitted at least one creation."""
        return self.runs_with_create / self.reps if self.reps else 0.0

    @property
    def volume(self) -> float:
        """Mean creations per run."""
        return self.total_created / self.reps if self.reps else 0.0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable view of the result."""
        return {
            "scenario": self.scenario_id,
            "expect_create": self.expect_create,
            "reps": self.reps,
            "create_rate": round(self.create_rate, 3),
            "volume": round(self.volume, 2),
            "errors": self.error_runs,
        }


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    """Aggregate per-scenario results into the report headline figures.

    Args:
        results: One entry per scenario.

    Returns:
        Noise on negatives, recall on positives, volumes, and the list of
        negatives that leaked (the actionable part of the report).
    """
    pos = [r for r in results if r.expect_create]
    neg = [r for r in results if not r.expect_create]
    return {
        "negative_noise_rate": (
            round(sum(r.runs_with_create for r in neg) / sum(r.reps for r in neg), 3)
            if neg
            else 0.0
        ),
        "negative_volume": (
            round(sum(r.total_created for r in neg) / sum(r.reps for r in neg), 2) if neg else 0.0
        ),
        "positive_recall": (
            round(sum(r.runs_with_create for r in pos) / sum(r.reps for r in pos), 3)
            if pos
            else 0.0
        ),
        "positive_volume": (
            round(sum(r.total_created for r in pos) / sum(r.reps for r in pos), 2) if pos else 0.0
        ),
        "leaking_negatives": sorted(r.scenario_id for r in neg if r.create_rate > 0),
        "missed_positives": sorted(r.scenario_id for r in pos if r.create_rate < 1.0),
    }


# =============================================================================
# Execution
# =============================================================================

_TOKENS: Counter[str] = Counter()


def _build_llm(llm_type: ExtractorType, knobs: dict[str, Any]) -> Any:
    """Instantiate the extraction LLM under an explicit, printed configuration.

    Args:
        llm_type: ``interest_extraction`` or ``memory_extraction``.
        knobs: provider/model/temperature/max_tokens/effort to force.

    Returns:
        A configured chat model.
    """
    from src.core.config import settings
    from src.core.llm_config_helper import get_llm_config_for_agent
    from src.core.reasoning_types import ReasoningEffortEnum
    from src.infrastructure.llm.factory import get_llm

    update: dict[str, Any] = {
        "provider": knobs["provider"],
        "model": knobs["model"],
        "temperature": knobs["temperature"],
        "max_tokens": knobs["max_tokens"],
        "reasoning_effort": (
            ReasoningEffortEnum(effort=knobs["effort"]) if knobs.get("effort") else None
        ),
    }
    config = get_llm_config_for_agent(settings, llm_type).model_copy(update=update)
    return get_llm(llm_type, config_override=config)


async def _run_once(llm: Any, prompt: str, parse: Any, label: Any) -> list[str]:
    """Invoke the LLM once and return one label per CREATE action."""
    result = await llm.ainvoke(prompt)
    usage = getattr(result, "usage_metadata", None) or {}
    _TOKENS["calls"] += 1
    _TOKENS["input"] += int(usage.get("input_tokens", 0))
    _TOKENS["output"] += int(usage.get("output_tokens", 0))
    return [label(a) for a in parse(result.text) if a.action == "create"]


async def _measure(
    scenarios: tuple[Scenario, ...],
    reps: int,
    template: str,
    render: Any,
    llm: Any,
    parse: Any,
    label: Any,
    now: str,
    show_items: bool,
) -> list[ScenarioResult]:
    """Run one battery and aggregate the outcomes."""
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        prompt = render(template, scenario, now)
        runs = await asyncio.gather(
            *[_run_once(llm, prompt, parse, label) for _ in range(reps)],
            return_exceptions=True,
        )
        res = ScenarioResult(scenario.id, scenario.expect_create, reps)
        for run in runs:
            if isinstance(run, BaseException):
                res.error_runs += 1
                continue
            if run:
                res.runs_with_create += 1
                res.total_created += len(run)
                res.samples.extend(run)
        results.append(res)
        verdict = "OK " if (res.create_rate > 0) == scenario.expect_create else "!! "
        print(f"  {verdict}{scenario.id:<26} {res.as_dict()}", flush=True)
        if show_items:
            for sample in dict.fromkeys(res.samples):
                print(f"        · {sample}", flush=True)
    return results


async def _amain(args: argparse.Namespace) -> int:
    """Load the config cache, run the requested batteries, print and dump."""
    from datetime import UTC, datetime

    from src.domains.agents.prompts import load_prompt
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.database.session import get_db_context

    import_all_models()
    async with get_db_context() as db:
        await LLMConfigOverrideCache.load_from_db(db)

    knobs = dict(PROFILES[args.profile])
    for key in ("model", "temperature", "effort"):
        if getattr(args, key) is not None:
            knobs[key] = getattr(args, key)
    if knobs.get("effort") in ("", "none-null"):
        knobs["effort"] = None

    now = datetime.now(tz=UTC).strftime("%d/%m/%Y %H:%M")
    report: dict[str, Any] = {"profile": args.profile, "knobs": knobs, "reps": args.reps}
    print(f"LLM: {knobs}\n")

    def _filtered(pool: tuple[Scenario, ...]) -> tuple[Scenario, ...]:
        if not args.scenario:
            return pool
        wanted = set(args.scenario)
        return tuple(s for s in pool if s.id in wanted)

    if args.battery in ("interests", "both"):
        from src.domains.interests.services.extraction_service import _parse_extraction_result

        template = (
            Path(args.interest_prompt).read_text(encoding="utf-8")
            if args.interest_prompt
            else str(load_prompt("interest_extraction_prompt"))
        )
        _assert_placeholders(template, INTEREST_PLACEHOLDERS, "interest_extraction_prompt")
        pool = INTEREST_HOLDOUT if args.set == "holdout" else INTEREST_SCENARIOS
        scenarios = _filtered(pool)
        if scenarios:
            print("=" * 78)
            print(f"INTERESTS  ({args.interest_prompt or '<shipped>'})")
            print("=" * 78)
            res = await _measure(
                scenarios,
                args.reps,
                template,
                _render_interest_prompt,
                _build_llm("interest_extraction", knobs),
                _parse_extraction_result,
                lambda a: f"{a.topic} [{a.category.value if a.category else '?'} {a.confidence}]",
                now,
                args.show_items,
            )
            report["interests"] = [r.as_dict() for r in res]
            report["interests_summary"] = summarize(res)
            print("\n--- interests summary ---")
            for key, value in report["interests_summary"].items():
                print(f"  {key:<22}: {value}")

    if args.battery in ("memory", "both"):
        from src.domains.agents.services.memory_extractor import (
            _parse_extraction_result as mem_parse,
        )

        template = (
            Path(args.memory_prompt).read_text(encoding="utf-8")
            if args.memory_prompt
            else str(load_prompt("memory_extraction_prompt"))
        )
        _assert_placeholders(template, MEMORY_PLACEHOLDERS, "memory_extraction_prompt")
        pool = MEMORY_HOLDOUT if args.set == "holdout" else MEMORY_SCENARIOS
        scenarios = _filtered(pool)
        if scenarios:
            print("\n" + "=" * 78)
            print(f"MEMORY  ({args.memory_prompt or '<shipped>'})")
            print("=" * 78)
            res = await _measure(
                scenarios,
                args.reps,
                template,
                _render_memory_prompt,
                _build_llm("memory_extraction", knobs),
                mem_parse,
                lambda a: f"{a.category} | {a.content}",
                now,
                args.show_items,
            )
            report["memory"] = [r.as_dict() for r in res]
            report["memory_summary"] = summarize(res)
            print("\n--- memory summary ---")
            for key, value in report["memory_summary"].items():
                print(f"  {key:<22}: {value}")

    calls = _TOKENS["calls"] or 1
    report["tokens_per_call"] = {
        "input": round(_TOKENS["input"] / calls, 1),
        "output": round(_TOKENS["output"] / calls, 1),
        "calls": _TOKENS["calls"],
    }
    print(f"\n  tokens_per_call       : {report['tokens_per_call']}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nJSON report written to {args.json_out}")
    return 0


def main() -> int:
    """Parse arguments and run the measurement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--battery", choices=("interests", "memory", "both"), default="both")
    parser.add_argument("--reps", type=int, default=5, help="Runs per scenario (default: 5)")
    parser.add_argument("--interest-prompt", help="Candidate interest prompt file")
    parser.add_argument("--memory-prompt", help="Candidate memory prompt file")
    parser.add_argument("--profile", choices=tuple(PROFILES), default="prod")
    parser.add_argument(
        "--set",
        choices=("tuned", "holdout"),
        default="tuned",
        help="'tuned' = the battery the prompts were written against; "
        "'holdout' = same classes, subjects no prompt has seen (default: tuned)",
    )
    parser.add_argument("--model", help="Force the model (overrides the profile)")
    parser.add_argument("--temperature", type=float, help="Force the temperature")
    parser.add_argument("--effort", help="Force the reasoning effort (e.g. off, high, max, low)")
    parser.add_argument("--scenario", action="append", help="Restrict to this scenario id")
    parser.add_argument("--show-items", action="store_true", help="Print what was created")
    parser.add_argument("--json-out", help="Write the full report as JSON")
    return asyncio.run(_amain(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
