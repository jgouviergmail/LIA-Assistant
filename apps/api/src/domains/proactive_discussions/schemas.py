"""Strict preferences and separate context/engagement model contracts.

Models marked MODEL-FACING below are read by a model as a JSON schema (a
structured-output contract or a tool parameter). They carry comments, never
docstrings or field descriptions: both become schema text, and changing what a
model reads is a measured decision, not documentation.
"""

from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    Field,
    StrictBool,
    StrictInt,
    TypeAdapter,
    field_validator,
    model_validator,
)

from src.core.constants import (
    DEFAULT_USER_DISPLAY_TIMEZONE,
    DISCUSSION_OPENING_MAX_CHARS,
    DISCUSSION_OPENING_PROOFS_MAX,
)
from src.domains.shared.discussion_sources import (
    DiscussionValue,
    NonEmpty,
    ResearchRequest,
    SensitiveTopic,
    SourceKey,
)


class DiscussionPolicy(DiscussionValue):
    """One account's discussion policy, read from its preferences and its timezone."""

    enabled: StrictBool = Field(default=False, description="LIA may start a discussion.")
    start_hour: Annotated[
        StrictInt, Field(ge=0, le=23, description="First local hour of the window.")
    ] = 9
    end_hour: Annotated[
        StrictInt,
        Field(ge=0, le=23, description="Local hour the window ends (excluded); may wrap."),
    ] = 20
    timezone: str = Field(
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        description="The account's IANA timezone, in which the hours are read.",
    )
    daily_max: Annotated[
        StrictInt | None, Field(ge=1, description="Most openings per local day; null: none.")
    ] = 2
    sources: tuple[SourceKey, ...] = Field(
        default=(), description="The sources the person allowed, each its own consent."
    )
    sensitive_topics: tuple[SensitiveTopic, ...] = Field(
        default=(), description="The sensitive topics the person explicitly allowed."
    )
    forbidden_topics: Annotated[
        tuple[Annotated[str, Field(min_length=1, max_length=160)], ...],
        Field(max_length=100, description="Topics the person asked LIA to avoid."),
    ] = ()
    paused_until: AwareDatetime | None = Field(
        default=None, description="Until when discussions are paused, if they are."
    )
    revision: Annotated[
        StrictInt, Field(ge=0, description="The revision a write must name to apply.")
    ] = 0

    @field_validator("timezone")
    @classmethod
    def timezone_exists(cls, value: str) -> str:
        """Refuse a timezone the IANA database does not know."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown timezone") from exc
        return value

    @model_validator(mode="after")
    def coherent_policy(self) -> Self:
        """Refuse an empty hour window and any duplicated consent or forbidden topic."""
        if self.start_hour == self.end_hour:
            raise ValueError("start and end hours must differ")
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("duplicate source consent")
        if len(set(self.sensitive_topics)) != len(self.sensitive_topics):
            raise ValueError("duplicate sensitive topic consent")
        if len({topic.strip().casefold() for topic in self.forbidden_topics}) != len(
            self.forbidden_topics
        ):
            raise ValueError("duplicate forbidden topic")
        return self


# MODEL-FACING (decision): LIA says nothing this time, and why.
class SkipDecision(DiscussionValue):
    action: Literal["skip"]
    reason: NonEmpty


# MODEL-FACING (decision): not now; the run is retried after the stated delay.
class DeferDecision(DiscussionValue):
    action: Literal["defer"]
    reason: NonEmpty
    retry_after_seconds: Annotated[StrictInt, Field(ge=1, le=86400)]


# MODEL-FACING (decision): open a discussion on a topic, citing offered evidence.
class EngageDecision(DiscussionValue):
    action: Literal["engage"]
    reason: NonEmpty
    topic: Annotated[str, Field(min_length=1, max_length=160)]
    sensitive_topics: tuple[SensitiveTopic, ...] = ()
    references: Annotated[
        tuple[NonEmpty, ...], Field(min_length=1, max_length=DISCUSSION_OPENING_PROOFS_MAX)
    ]

    @field_validator("references")
    @classmethod
    def independent_references(cls, references: tuple[str, ...]) -> tuple[str, ...]:
        """Refuse an engagement that cites the same evidence twice."""
        if len(references) != len(set(references)):
            raise ValueError("duplicate evidence reference")
        return references


DiscussionDecision = Annotated[
    SkipDecision | DeferDecision | EngageDecision, Field(discriminator="action")
]
_DECISION_ADAPTER: TypeAdapter[DiscussionDecision] = TypeAdapter(DiscussionDecision)


# MODEL-FACING (context): the context is enough; these references support it.
class ReadyContext(DiscussionValue):
    status: Literal["ready"]
    references: Annotated[tuple[NonEmpty, ...], Field(min_length=1, max_length=100)]


# MODEL-FACING (context): one more bounded research wave is needed.
class ResearchContext(DiscussionValue):
    status: Literal["research"]
    requests: Annotated[tuple[ResearchRequest, ...], Field(min_length=1, max_length=4)]


# MODEL-FACING (context): nothing worth a discussion can be built, and why.
class InsufficientContext(DiscussionValue):
    status: Literal["insufficient"]
    reason: NonEmpty


ContextResolution = Annotated[
    ReadyContext | ResearchContext | InsufficientContext, Field(discriminator="status")
]

DiscussionFeedback = Literal["useful", "not_now", "avoid_topic", "incorrect"]


class PriorOpening(DiscussionValue):
    """A previous opening shown to the decision, and what became of it."""

    created_at: AwareDatetime
    content: Annotated[str, Field(min_length=1, max_length=DISCUSSION_OPENING_MAX_CHARS)]
    state: Literal["pending", "engaged", "dismissed", "expired"]
    feedback: DiscussionFeedback | None = None


_CONTEXT_ADAPTER: TypeAdapter[ContextResolution] = TypeAdapter(ContextResolution)


def parse_decision(value: object) -> DiscussionDecision:
    """Validate a raw decision into its skip, defer or engage variant.

    Args:
        value: The decoded decision.

    Returns:
        The validated decision.

    Raises:
        pydantic.ValidationError: The value matches no variant.
    """
    return _DECISION_ADAPTER.validate_python(value)


def parse_context_resolution(value: object) -> ContextResolution:
    """Validate a raw context resolution into its ready, research or insufficient variant.

    Args:
        value: The decoded resolution.

    Returns:
        The validated resolution.

    Raises:
        pydantic.ValidationError: The value matches no variant.
    """
    return _CONTEXT_ADAPTER.validate_python(value)
