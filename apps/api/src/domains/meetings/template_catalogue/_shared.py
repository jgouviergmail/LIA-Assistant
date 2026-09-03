"""Shapes and shared instructions of the built-in templates (ADR-259).

One wording, one place: an instruction several templates share (summary,
decisions, actions, risks…) is a constant here, so the templates cannot drift
from each other. The kind aliases keep the category modules readable.
"""

from __future__ import annotations

from typing import NamedTuple

from src.domains.meetings.schemas import SectionKind, TemplateCategory


class BuiltinSection(NamedTuple):
    """One section of a built-in template."""

    key: str
    kind: SectionKind
    instruction: str


class BuiltinTemplate(NamedTuple):
    """One catalogue template."""

    key: str
    category: TemplateCategory
    auto_selectable: bool
    sections: tuple[BuiltinSection, ...]


P = SectionKind.PARAGRAPH
B = SectionKind.BULLETS
T = SectionKind.TOPICS
A = SectionKind.ACTION_ITEMS
TR = SectionKind.TRANSCRIPT

SUMMARY = (
    "A clear, concise overall summary of the exchange: purpose, what was covered, "
    "outcome. Three to six sentences, no bullet points."
)
TOPICS = (
    "Every distinct topic discussed, each with a short factual summary of what "
    "was said about it. One entry per topic, in the order they came up."
)
DECISIONS = (
    "Decisions actually taken during the meeting, one per bullet. Only what was "
    "explicitly decided — never a proposal that was left open."
)
ACTIONS = (
    "Concrete actions, tasks and commitments, each with its owner when named and "
    "its deadline as an absolute date when one was given."
)
RISKS = (
    "Risks, blockers, disagreements, points of vigilance and anything flagged as "
    "sensitive or urgent. Empty when nothing of the kind was raised."
)
OPEN_QUESTIONS = (
    "Questions raised and left unanswered, items postponed, and follow-ups to "
    "clarify. Empty when everything was settled."
)
NEXT_STEPS = (
    "What happens next, as concrete actions with the owner when named and the "
    "deadline as an absolute date when one was given."
)
FOLLOW_UPS = (
    "Actions needing attention that are not direct tasks: meetings to schedule, "
    "research to do, people to inform. Empty when there is none."
)
TRANSCRIPT_CLEAN = (
    "The complete exchange, turn by turn, in the speakers' own language, made clean "
    "and readable: remove hesitations, fillers, false starts and repetitions; apply "
    "the speaker's own self-corrections; fix punctuation and obvious slips of the "
    "tongue. Keep every idea, figure, name and nuance; never summarize, never add, "
    "never change the register."
)
TRANSCRIPT_PRO = (
    "The complete exchange, turn by turn, in the speakers' own language, rewritten "
    "in a clear professional register: complete sentences, precise vocabulary, no "
    "fillers, no repetitions, the speaker's self-corrections applied. Keep every "
    "idea, figure, name and commitment; never summarize or add; keep who said what."
)
DOCUMENTS = (
    "Documents, information or proofs the user must provide, one per bullet, with "
    "the deadline when stated."
)
