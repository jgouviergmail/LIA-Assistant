"""The writer's answer: spoken lines, each with a voice, a delivery and its sources.

This is the shape the MODEL is asked for, so it carries no bound (a
``max_length`` in a structured-output schema refuses the whole answer where the
doctrine says repair, and not every provider accepts the keyword in strict
mode). The bounds are published in the writer's prompt and enforced, line by
line, by :mod:`src.domains.radio.verification` — which repairs what is
mechanical and drops or refuses the rest, saying which rule decided.

Class docstrings reach the model as schema descriptions, so they stay one line.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.domains.radio.formats import RadioRole


class Energy(StrEnum):
    """How much drive a line carries."""

    CALM = "calm"
    NEUTRAL = "neutral"
    LIVELY = "lively"


class Pace(StrEnum):
    """How fast a line is spoken."""

    SLOW = "slow"
    NORMAL = "normal"
    BRISK = "brisk"


class Tone(StrEnum):
    """The colour of a line."""

    NEUTRAL = "neutral"
    WARM = "warm"
    SERIOUS = "serious"
    UPBEAT = "upbeat"
    CONCERNED = "concerned"


#: The words each delivery field accepts.
_DELIVERY_WORDS: Final[dict[str, frozenset[str]]] = {
    "energy": frozenset(member.value for member in Energy),
    "pace": frozenset(member.value for member in Pace),
    "tone": frozenset(member.value for member in Tone),
}


class RadioDelivery(BaseModel):
    """How a line should sound."""

    model_config = ConfigDict(frozen=True)

    energy: Energy = Field(default=Energy.NEUTRAL, description="Drive of the line.")
    pace: Pace = Field(default=Pace.NORMAL, description="Speed of the line.")
    tone: Tone = Field(default=Tone.NEUTRAL, description="Colour of the line.")

    @field_validator("energy", "pace", "tone", mode="before")
    @classmethod
    def _unknown_is_the_default(cls, value: object, info: ValidationInfo) -> object:
        # How a line sounds is cosmetic: a word off the vocabulary reads as the
        # default rather than throwing the whole script away (a repair —
        # measured 2026-09-26: two of four scripts of one model family were
        # refused for ``delivery.energy`` alone).
        name = str(info.field_name)
        if isinstance(value, str) and value in _DELIVERY_WORDS[name]:
            return value
        return cls.model_fields[name].default


class ScriptPart(StrEnum):
    """Where a line sits: over the opening music, in the body, over the closing music."""

    INTRO = "intro"
    BODY = "body"
    OUTRO = "outro"


class LineKind(StrEnum):
    """What a line asserts — which decides what it must cite."""

    #: States something from the facts: cites at least one non-analysis fact.
    FACT = "fact"
    #: States the expert analysis: cites at least one analysis fact.
    ANALYSIS = "analysis"
    #: A commentator's view on the story it cites, said as a view: cites at
    #: least one non-analysis fact, and only a commentator voices it — the
    #: editorialist, a speaker of a debate or a discussion (``OPINION_ROLES``).
    OPINION = "opinion"
    #: Links, introduces, hands over: asserts nothing about the world.
    TRANSITION = "transition"


class ScriptLine(BaseModel):
    """One spoken line."""

    model_config = ConfigDict(frozen=True)

    role: RadioRole = Field(description="Who speaks the line.")
    part: ScriptPart = Field(description="Intro and outro lines are spoken over music.")
    kind: LineKind = Field(description="fact, analysis, opinion or transition.")
    text: str = Field(description="What is said, written for the ear.")
    delivery: RadioDelivery = Field(
        default_factory=RadioDelivery, description="How it should sound."
    )
    refs: list[str] = Field(
        default_factory=list, description="Ids of the facts the line relies on."
    )


class ScriptDraft(BaseModel):
    """A radio segment's script."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="Short programme title shown to the listener.")
    lines: list[ScriptLine] = Field(description="The lines, in the order they are spoken.")
