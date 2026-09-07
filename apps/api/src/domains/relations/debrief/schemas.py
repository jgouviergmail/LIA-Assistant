"""The debrief's wire and storage contracts.

Three shapes, deliberately separate:

- :class:`DebriefDraft` is what the MODEL is asked for, and it carries no bound
  at all: a bound in a schema REFUSES where the doctrine says to REPAIR, and
  not every provider accepts the keyword in strict mode.
- :class:`DebriefBody` is what the reader is served and what the row stores,
  trimmed into shape by :meth:`DebriefDraft.to_body`. It is versioned, because
  a reader that cannot understand a shape must rebuild rather than render half
  of it.
- :class:`RelationDebriefRead` is what the API answers. It carries the body
  *plus* everything that makes the body honest — when it was written, under
  which scope, and what could not be read — because a synthesis without its
  provenance is a claim.

No user-facing string is ever pre-translated here: the frontend owns the
labels and resolves them from the active locale (frontend contract). Only the
model's own prose travels, and it was written in the user's language.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.core.constants import (
    RELATION_DEBRIEF_BODY_VERSION,
    RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
    RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
)
from src.core.llm_usage import LLMUsage


class DebriefStatus(str, Enum):
    """What the API says about one relationship's debrief.

    ``ABSENT`` is not one of the stored states: it means no row exists, which
    the reader sees as "not built yet" and the chat sees as "inject nothing".
    ``DISABLED`` is the account's own decision, and must never be rendered as
    an error — a feature the user turned off is working as asked.
    """

    ABSENT = "absent"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    EMPTY = "empty"
    DISABLED = "disabled"


#: Longest each prose field may be once stored. Enforced by TRIMMING, never by
#: refusing: see :meth:`DebriefDraft.to_body`.
_HEADLINE_MAX = 300
_WHERE_WE_STAND_MAX = 1500
_NEXT_STEP_MAX = 400


def _clip(value: str | None, limit: int) -> str | None:
    """Cut one prose field to its bound, on a word boundary when it can.

    The ellipsis is counted IN the bound: a clip that returned ``limit + 1``
    characters would need the stored contract to be one character looser than
    the published one, and two nearly-equal numbers is how they drift.

    Args:
        value: The model's prose, or None.
        limit: Longest the result may be, ellipsis included.

    Returns:
        The text within its bound, or None.
    """
    if value is None:
        return None
    text = value.strip()
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    return f"{head.rsplit(' ', 1)[0] or head}…"


# ``DebriefDraft`` carries no bound at all, and its DOCSTRING is deliberately
# one line — Pydantic sends both to the model as the schema's description, so
# anything written here is prompt material the reader pays for. The reasoning
# belongs in this comment instead:
#
# - **a bound in a schema REFUSES, it does not trim.** A model answering six
#   open points where five were asked would fail validation and take the whole
#   build down over a display detail. What is mechanically repairable is
#   repaired, never reported as a defect — ADR-184's doctrine, the same one the
#   planner applies to out-of-range parameters.
# - **not every provider accepts the keyword.** The length and item-count
#   constraints are not universally supported in strict structured-output mode,
#   and a schema a provider rejects fails EVERY build on that slot — a whole
#   capability lost to something Python enforces for free.
#
# The bounds are still PUBLISHED to the writer in its own prompt (ADR-184):
# what ``to_body`` will trim is what the model could read.
class DebriefDraft(BaseModel):
    """A written relationship debrief."""

    model_config = ConfigDict(frozen=True)

    headline: str = Field(
        description="One sentence, under 15 words: where the relationship stands."
    )
    where_we_stand: str = Field(
        description="Two to three sentences on the state of the relationship."
    )
    open_points: list[str] = Field(
        default_factory=list,
        description="What is genuinely open. Empty when nothing is.",
    )
    suggested_next_step: str | None = Field(
        default=None,
        description="One concrete next action, or null when the evidence suggests none.",
    )
    notable_facts: list[str] = Field(
        default_factory=list,
        description="Durable facts worth remembering. Empty when the evidence carries none.",
    )

    def to_body(self) -> DebriefBody:
        """Repair the draft into the bounded shape the reader is served.

        Returns:
            The synthesis, trimmed to what the contract publishes.
        """
        return DebriefBody(
            headline=_clip(self.headline, _HEADLINE_MAX) or "",
            where_we_stand=_clip(self.where_we_stand, _WHERE_WE_STAND_MAX) or "",
            open_points=[
                point.strip()
                for point in self.open_points[:RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT]
                if point.strip()
            ],
            suggested_next_step=_clip(self.suggested_next_step, _NEXT_STEP_MAX) or None,
            notable_facts=[
                fact.strip()
                for fact in self.notable_facts[:RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT]
                if fact.strip()
            ],
        )


class DebriefBody(BaseModel):
    """The synthesis as the reader is served it, and as the row stores it.

    Bounded — but the bounds are reached by TRIMMING in
    :meth:`DebriefDraft.to_body`, never by refusing a model's answer.
    """

    model_config = ConfigDict(frozen=True)

    headline: str = Field(
        description="One sentence, under 15 words: where the relationship stands.",
        max_length=_HEADLINE_MAX,
    )
    where_we_stand: str = Field(
        description="Two to three sentences on the state of the relationship.",
        max_length=_WHERE_WE_STAND_MAX,
    )
    open_points: list[str] = Field(
        default_factory=list,
        max_length=RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
        description="What is genuinely open. Empty when nothing is.",
    )
    suggested_next_step: str | None = Field(
        default=None,
        max_length=_NEXT_STEP_MAX,
        description="One concrete next action, or null when the evidence suggests none.",
    )
    notable_facts: list[str] = Field(
        default_factory=list,
        max_length=RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
        description="Durable facts worth remembering. Empty when the evidence carries none.",
    )


class StoredDebriefBody(DebriefBody):
    """A body as it sits in the column: the synthesis plus its shape version."""

    version: int = Field(
        default=RELATION_DEBRIEF_BODY_VERSION,
        description="Payload shape; a reader that cannot read it rebuilds.",
    )


class RelationDebriefRead(BaseModel):
    """One relationship's debrief, with everything that makes it honest."""

    model_config = ConfigDict(frozen=True)

    status: DebriefStatus
    person: str = Field(description="Spelling the debrief was written about.")
    body: DebriefBody | None = Field(
        default=None,
        description=(
            "The synthesis. Present on a FAILED status too, when a previous "
            "one still stands: a rebuild that failed must not turn 'I could "
            "not refresh this' into 'there is nothing'."
        ),
    )
    generated_at: datetime | None = Field(
        default=None,
        description="UTC instant the body was written — never the instant it was read.",
    )
    generated_for: date | None = Field(
        default=None, description="The user's local date this debrief belongs to."
    )
    usage: LLMUsage | None = Field(
        default=None,
        description=(
            "What the call that wrote this body cost. None — never zeros — "
            "when the row cannot say: a cost of 0 is a claim, and a debrief "
            "written before this was recorded made none."
        ),
    )
    sections_used: list[str] = Field(
        default_factory=list, description="Sources the debrief actually read."
    )
    unavailable: list[str] = Field(
        default_factory=list,
        description="Sources asked for that could not be read — stated, never implied away.",
    )
    can_rebuild: bool = Field(
        default=False,
        description=(
            "Whether asking again would do anything right now. False while a "
            "build is in flight or a failure is cooling down, so the control "
            "is never offered for an action that would be refused."
        ),
    )
