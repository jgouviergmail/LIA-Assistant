"""Built-in templates — category ``analysis`` (ADR-259)."""

from __future__ import annotations

from src.domains.meetings.schemas import TemplateCategory
from src.domains.meetings.template_catalogue._shared import (
    B,
    BuiltinSection,
    BuiltinTemplate,
    P,
    T,
)

_C = TemplateCategory.ANALYSIS

TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        "intent_analysis",
        _C,
        True,
        (
            BuiltinSection(
                "primary_intent",
                P,
                "As a seasoned diplomat reading past the literal words: the most likely "
                "underlying intent of the main speaker (the job to be done), stated in "
                "two to four sentences, with a confidence level: high, medium or low.",
            ),
            BuiltinSection(
                "diagnostic_cues",
                B,
                "The evidence: observable behaviours and quoted passages, read through "
                "emotional cadence, the texture of pauses and hesitations, over-explaining "
                "or minimizing, and the cultural or formal context where indirectness is "
                "normal. One cue per bullet with its quote.",
            ),
            BuiltinSection(
                "response_strategy",
                P,
                "Not a reply but a strategic approach to navigate the conversation given "
                "the inferred intent: what to acknowledge, what to ask, what to avoid.",
            ),
        ),
    ),
    BuiltinTemplate(
        "speaker_psychology",
        _C,
        True,
        (
            BuiltinSection(
                "participants_roles",
                T,
                "One entry per participant: their role in the conversation from their "
                "contributions, their language and communication style (word choice, "
                "tone, sentence structure) and what it suggests about confidence and "
                "assertiveness, and the emotional states shown and how they evolved.",
            ),
            BuiltinSection(
                "personality_traits",
                T,
                "One entry per participant: the main personality traits inferred through "
                "the Big Five, each backed by an example from the transcript, presented as "
                "observations, plus the most likely MBTI profile stated as a hypothesis.",
            ),
            BuiltinSection(
                "strengths_weaknesses",
                T,
                "One entry per participant: psychological strengths and weaknesses shown "
                "(empathy, reasoning, defensiveness, flexibility), each backed by a quote.",
            ),
            BuiltinSection(
                "group_dynamics",
                P,
                "The interaction dynamics: power imbalances, alliances, conflicts, levels "
                "of empathy and social roles, as the exchange shows them.",
            ),
            BuiltinSection(
                "cognitive_patterns",
                B,
                "Cognitive patterns and biases visible in the reasoning and decisions "
                "(confirmation bias, anchoring, particular thinking styles), each with the "
                "passage that shows it.",
            ),
            BuiltinSection(
                "recommendations",
                B,
                "The main psychological themes and neutral, evidence-based recommendations "
                "to improve communication. This is an observation from language, not a "
                "diagnosis: say so in the first bullet.",
            ),
        ),
    ),
    BuiltinTemplate(
        "power_dynamics",
        _C,
        True,
        (
            BuiltinSection(
                "influence_map",
                T,
                "One entry per participant: the influence they actually exert, read from "
                "behaviour rather than titles — speaking turns, interruptions, whose ideas "
                "get adopted, who defers to whom — with the evidence.",
            ),
            BuiltinSection(
                "key_moments",
                B,
                "The moments where influence shifted or concentrated: who did what, and "
                "what changed as a result. One moment per bullet with its timestamp.",
            ),
            BuiltinSection(
                "dynamics_summary",
                P,
                "A dynamic reading of the power structure — how influence moved and where "
                "it settled over the exchange — rather than a static chart.",
            ),
        ),
    ),
    BuiltinTemplate(
        "behavior_analyst",
        _C,
        True,
        (
            BuiltinSection(
                "behavioral_profiles",
                T,
                "One entry per speaker with substantial dialogue (skip silent or minor "
                "ones): their one or two primary behavioural needs among significance, "
                "acceptance, approval, intelligence, pity and strength, with supporting "
                "evidence; the probable emotional driver; specific behavioural indicators; "
                "an effective influence strategy. Observable behaviour and language only, "
                "no personality typology. When the evidence is thin, say the data is "
                "insufficient for that speaker.",
            ),
            BuiltinSection(
                "operational_application",
                P,
                "One practical application of these profiles: a rapport-building "
                "approach, a negotiation angle, a recruiting posture or a preparation for "
                "the next exchange. Tactical, never academic.",
            ),
        ),
    ),
    BuiltinTemplate(
        "quantitative_data",
        _C,
        True,
        (
            BuiltinSection(
                "data_points",
                T,
                "As a meticulous data analyst: every number spoken, one entry each. The "
                "title is the data element named from its surrounding description "
                "(frequency first, time first), then the value exactly as spoken and an "
                "inferred unit (days, %, EUR, items). The summary is the context: "
                "assumptions, decisions or debates around that figure. Resolve indirect "
                "mentions ('that number') to their origin.",
            ),
            BuiltinSection(
                "data_notes",
                B,
                "Figures that stayed ambiguous, contradictions between numbers, and what "
                "would be needed to settle them. Empty when everything was clear.",
            ),
        ),
    ),
)
