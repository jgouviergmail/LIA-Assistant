"""Typed compact derived knowledge. No source body is a persisted field.

ContextProposal is MODEL-FACING: it is part of the context call's structured-output
schema, so it carries comments, never a docstring or field descriptions (they would
become schema text and change what the model reads without a measurement).
"""

from datetime import date
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from src.core.recurrence import RecurrenceSpec
from src.domains.shared.discussion_sources import (
    CoverageKind,
    DiscussionValue,
    GraphRecurrence,
    NonEmpty,
    OptionalNonEmpty,
    SensitiveTopic,
    SourceKey,
    SourceStatus,
)

ContextKind = Literal["observation", "episode", "pattern"]
Qualification = Literal[
    "planned", "reported", "observed", "declared", "possible", "contradicted", "unknown"
]
Summary = Annotated[str, Field(min_length=1, max_length=1200)]
#: Why one proposal was set aside, alone: while its answer was read (beyond the
#: published cap, a shape the contract refuses once its mechanical defects are
#: repaired), or while it was published (a reference not admitted, a refused topic, a
#: qualification its evidence does not carry, a pattern over two subjects, a second
#: proposal making the same item).
ProposalRefusal = Literal[
    "beyond_cap",
    "unreadable",
    "inadmissible_reference",
    "refused_topic",
    "unsupported_qualification",
    "mixed_subjects",
    "duplicate_item",
]


# MODEL-FACING (context call): one observation, episode or pattern the model proposes,
# anchored on evidence it was shown.
class ContextProposal(DiscussionValue):
    kind: ContextKind
    summary: Summary
    qualification: Qualification
    sensitive_topics: tuple[SensitiveTopic, ...] = ()
    anchor: NonEmpty
    references: Annotated[tuple[NonEmpty, ...], Field(min_length=1, max_length=32)]
    declaration_quote: Annotated[str | None, Field(min_length=1, max_length=400)] = None

    @model_validator(mode="after")
    def supported_anchor(self) -> Self:
        """Refuse an anchor outside the references, a duplicated reference, or a
        multi-source observation.
        """
        if self.anchor not in self.references or len(set(self.references)) != len(self.references):
            raise ValueError("anchor must be supported and references distinct")
        if self.kind == "observation" and len(self.references) != 1:
            raise ValueError("an observation has one source object")
        return self


class ContextCandidate(DiscussionValue):
    """Validated proposals, with the policy, epoch and generation they were built on."""

    policy_revision: Annotated[StrictInt, Field(ge=0)]
    context_epoch: Annotated[StrictInt, Field(ge=0)]
    base_generation: Annotated[StrictInt, Field(ge=0)]
    proposals: Annotated[tuple[ContextProposal, ...], Field(max_length=100)]


class ContextEvidenceLink(DiscussionValue):
    """The body-free proof of one evidence: identity, version, dates and authority.

    It is what a context item, an observation and an opening cite: enough to read
    the evidence again and to check it did not change, never its content.
    """

    interpreted_context_epoch: Annotated[
        StrictInt | None, Field(ge=0, description="The context epoch it was interpreted in.")
    ] = None
    interpreted_policy_revision: Annotated[
        StrictInt | None, Field(ge=0, description="The policy revision it was interpreted under.")
    ] = None
    interpretation_signature: OptionalNonEmpty = Field(
        default=None,
        description="What its interpretation depended on: sources, topics, clock, language.",
    )
    directives_revision: OptionalNonEmpty = Field(
        default=None, description="The rules it was interpreted under."
    )
    root: NonEmpty = Field(description="The evidence's identity key.")
    reference: NonEmpty = Field(description="The reference the evidence was offered under.")
    source: SourceKey = Field(description="The source it came from.")
    source_account: NonEmpty = Field(description="The source account that holds it.")
    object_id: NonEmpty = Field(description="The object's id in its source.")
    version: NonEmpty = Field(description="The version read; any change makes a new one.")
    observed_at: AwareDatetime = Field(description="When LIA read it.")
    recorded_at: AwareDatetime | None = Field(
        default=None, description="When the source recorded it, when known."
    )
    occurred_at: AwareDatetime | None = Field(
        default=None, description="When the fact happened, when known."
    )
    interval_start: AwareDatetime | None = Field(
        default=None, description="Start of the period it covers, when it has one."
    )
    interval_end: AwareDatetime | None = Field(
        default=None, description="End of the period it covers, when it has one."
    )
    expires_at: AwareDatetime = Field(description="When the proof stops being usable.")
    assertion: Literal["planned", "reported", "observed", "inferred", "unknown"] = Field(
        description="How the source stated the fact."
    )
    subject_id: OptionalNonEmpty = Field(
        default=None, description="The person or thing it is about, when known."
    )
    series_id: OptionalNonEmpty = Field(
        default=None, description="The recurring series it belongs to, if any."
    )
    original_start: AwareDatetime | None = Field(
        default=None, description="A moved occurrence's original instant."
    )
    original_date: date | None = Field(
        default=None, description="A moved all-day occurrence's original date."
    )
    planned_date: date | None = Field(
        default=None, description="The civil date it is planned for, when all-day."
    )
    occurrence_state: Literal["scheduled", "cancelled", "reported_complete", "unknown"] = Field(
        default="unknown", description="What the source says became of it."
    )
    recurrence_rule: Annotated[
        str | None, Field(max_length=1000, description="Its RRULE, when it repeats.")
    ] = None
    recurrence_spec: RecurrenceSpec | None = Field(
        default=None, description="Its recurrence in LIA's own vocabulary, when it repeats."
    )
    native_recurrence: GraphRecurrence | None = Field(
        default=None, description="Its Microsoft Graph recurrence, when it repeats."
    )
    category: OptionalNonEmpty = Field(
        default=None, description="The source's own category for it."
    )
    usage_nuance: Annotated[
        str | None,
        Field(max_length=300, description="How it may be used, as the source states it."),
    ] = None
    emotional_weight: Annotated[
        StrictInt | None,
        Field(ge=-10, le=10, description="The weight the source recorded, -10 to 10."),
    ] = None
    required_sources: tuple[SourceKey, ...] = Field(
        default=(), description="Other sources that must be allowed to use it."
    )
    sensitive_topics: tuple[SensitiveTopic, ...] = Field(
        default=(), description="The sensitive topics it touches."
    )
    support_roots: tuple[NonEmpty, ...] = Field(
        default=(), description="The identity keys of what it rests on."
    )


class SourceCoverage(DiscussionValue):
    """What the latest read of one source covered: its window, status and cursor."""

    source: SourceKey = Field(description="The source.")
    start: AwareDatetime = Field(description="Start of the window read.")
    end: AwareDatetime = Field(description="End of the window read.")
    read_at: AwareDatetime = Field(description="When it was read.")
    status: SourceStatus = Field(description="How the read ended.")
    kind: CoverageKind = Field(description="What kind of coverage the read gives.")
    complete: StrictBool = Field(description="The window was read whole, not a page.")
    cursor: Annotated[
        str | None, Field(max_length=4096, description="Where the next page starts.")
    ] = None
    revision: OptionalNonEmpty = Field(
        default=None, description="The source's revision marker, when it has one."
    )


class ContextItem(DiscussionValue):
    """One derived context item, its qualification and the proofs it rests on."""

    id: UUID = Field(description="Stable for its kind and anchor.")
    kind: ContextKind = Field(description="Observation, episode or pattern.")
    summary: Summary = Field(description="What LIA understood, in a sentence or two.")
    qualification: Qualification = Field(description="How far the evidence supports it.")
    revision: Annotated[StrictInt, Field(ge=1, description="Moves when it changes.")]
    generation: Annotated[StrictInt, Field(ge=1, description="The generation it joined.")]
    proofs: Annotated[
        tuple[ContextEvidenceLink, ...],
        Field(min_length=1, max_length=32, description="The evidence it rests on."),
    ]
    excluded: StrictBool = Field(
        default=False, description="A non-use choice excludes it (its own or inherited)."
    )
    explicitly_excluded: StrictBool = Field(
        default=False, description="The non-use choice was made on this item itself."
    )


class ContextExclusion(DiscussionValue):
    """One non-use choice: the item it was made on and the roots it excludes."""

    item_id: UUID = Field(description="The item the choice was made on.")
    roots: tuple[NonEmpty, ...] = Field(description="The roots it excludes.")


class ContextGeneration(DiscussionValue):
    """One page of the derived context, its exclusions and the versions it belongs to."""

    generation: Annotated[
        StrictInt, Field(ge=0, description="Moves with every change of the context.")
    ]
    context_epoch: Annotated[
        StrictInt, Field(ge=0, description="Moves with every rebuild request or purge.")
    ]
    forgotten_at: AwareDatetime | None = Field(
        default=None, description="When the whole context was last purged."
    )
    refresh_requested: StrictBool = Field(
        default=False, description="A rebuild is requested and not yet done."
    )
    items: tuple[ContextItem, ...] = Field(default=(), description="This page's items.")
    exclusions: tuple[ContextExclusion, ...] = Field(
        default=(), description="This page's non-use choices."
    )
    coverage: tuple[SourceCoverage, ...] = Field(
        default=(), description="What the latest read of each source covered."
    )
    total: Annotated[
        StrictInt, Field(ge=0, description="Every item of the same filter, not this page.")
    ] = 0
    next_cursor: UUID | None = Field(
        default=None, description="The after_id of the next item page, if any."
    )
    exclusions_total: Annotated[
        StrictInt, Field(ge=0, description="Every item that carries a non-use choice.")
    ] = 0
    exclusions_next_cursor: UUID | None = Field(
        default=None, description="The after_exclusion_id of the next page, if any."
    )


class ContextPurgePreview(DiscussionValue):
    """What a purge would remove, counted against the context the person read."""

    context_epoch: Annotated[StrictInt, Field(ge=0, description="The epoch counted.")]
    generation: Annotated[StrictInt, Field(ge=0, description="The generation counted.")]
    selected_count: Annotated[
        StrictInt, Field(ge=0, description="The items selected (all, for a whole purge).")
    ]
    affected_count: Annotated[
        StrictInt, Field(ge=0, description="The items removed, dependants included.")
    ]


class ContextControls(DiscussionValue):
    """The person's controls a run applies before reading: exclusions and forgetting."""

    epoch: Annotated[StrictInt, Field(ge=0)]
    generation: Annotated[StrictInt, Field(ge=0)]
    forgotten_at: AwareDatetime | None = None
    excluded_roots: frozenset[str] = frozenset()
    forgotten_versions: dict[str, str] = Field(default_factory=dict)
