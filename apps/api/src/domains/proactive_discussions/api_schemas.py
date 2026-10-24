"""Session API contracts, shared by personal UI and the internal command services."""

from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, model_validator

from src.domains.proactive_discussions.run_types import RunReason, RunState
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.shared.discussion_sources import (
    DiscussionValue,
    ReadOperation,
    SourceKey,
    SourceStatus,
)


class SourceOption(DiscussionValue):
    """One source the settings page offers: what it reads and what it also needs."""

    key: SourceKey = Field(description="The source.")
    operations: tuple[ReadOperation, ...] = Field(description="The reads it offers.")
    indivisible: StrictBool = Field(description="It is used as one indivisible whole.")
    dependencies: tuple[SourceKey, ...] = Field(
        default=(), description="The sources it also needs allowed."
    )


class DiscussionSettingsResponse(DiscussionValue):
    """The settings page: the policy, the source catalogue and what the instance offers."""

    policy: DiscussionPolicy = Field(description="The person's policy.")
    sources: tuple[SourceOption, ...] = Field(description="Every source, in catalogue order.")
    producer_enabled: StrictBool = Field(
        description="The operator's switch lets discussions run on this instance."
    )
    budget_configured: StrictBool = Field(
        description="The three spending limits are set; nothing starts without them."
    )
    pause_hours: Annotated[
        StrictInt,
        Field(ge=1, description="Hours a pause lasts, as the instance configures it."),
    ]


class DiscussionSettingsUpdate(DiscussionValue):
    """A sparse policy change, against the revision it was made from."""

    expected_revision: Annotated[
        StrictInt, Field(ge=0, description="The policy revision the change was made against.")
    ]
    changes: DiscussionPolicyPatch = Field(description="The fields to change.")


class ContextUseUpdate(DiscussionValue):
    """Exclude one context item, or allow it again, against the context the person read."""

    usable: StrictBool = Field(description="Allow the item (true) or exclude it (false).")
    expected_epoch: Annotated[StrictInt, Field(ge=0, description="The epoch read.")]
    expected_revision: Annotated[
        StrictInt | None, Field(ge=1, description="The item revision read; needed to exclude.")
    ] = None

    @model_validator(mode="after")
    def exclusion_has_revision(self) -> Self:
        """Refuse an exclusion that does not name the item's current revision."""
        if not self.usable and self.expected_revision is None:
            raise ValueError("excluding an item requires its current revision")
        return self


class ContextEpochRequest(DiscussionValue):
    """A context command against the epoch the person read."""

    expected_epoch: Annotated[StrictInt, Field(ge=0, description="The epoch read.")]


class ContextPurgeRequest(ContextEpochRequest):
    """A purge of the whole context or of selected items, against the context read."""

    expected_generation: Annotated[
        StrictInt, Field(ge=0, description="The context generation read.")
    ]
    selection: Annotated[
        tuple[UUID, ...] | None,
        Field(min_length=1, max_length=100, description="The items, or none for all."),
    ] = None

    @model_validator(mode="after")
    def distinct_selection(self) -> Self:
        """Refuse a selection that names an item twice."""
        if self.selection is not None and len(set(self.selection)) != len(self.selection):
            raise ValueError("duplicate context selection")
        return self


Count = Annotated[StrictInt, Field(ge=0)]
Euros = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class RunUsage(DiscussionValue):
    """What one run cost, read from the run's own ledger row (the chat meter's figures)."""

    tokens_in: Count = Field(description="Prompt tokens billed to the account.")
    tokens_out: Count = Field(description="Completion tokens billed to the account.")
    tokens_cache: Count = Field(description="Cached prompt tokens billed to the account.")
    google_requests: Count = Field(description="Google Maps Platform calls billed (weather).")
    cost_eur: Euros = Field(description="Everything the platform paid for the run, in euros.")


class RunStats(DiscussionValue):
    """What a run read and interpreted: counts only, never content."""

    pages: dict[SourceStatus, Count] = Field(
        default_factory=dict, description="The pages last read, by status."
    )
    facts_read: Count = Field(default=0, description="The facts those pages held.")
    facts_admitted: Count = Field(default=0, description="Those the person's controls admitted.")
    facts_offered: Count = Field(default=0, description="The facts sent to context calls.")
    facts_unclassified: Count = Field(
        default=0, description="Those a call left without a topic label, kept out of its pass."
    )
    context_calls: Count = Field(default=0, description="The context calls made.")
    proposals: Count = Field(default=0, description="The proposals those calls returned.")
    proposals_refused: Count = Field(
        default=0,
        description="Those set aside one by one: unreadable, or beyond their evidence.",
    )
    research_refused: Count = Field(
        default=0, description="The research requests the policy or the pages refused."
    )
    context_updates: Count = Field(
        default=0, description="The publications that updated the context (its generation)."
    )
    items: Count = Field(default=0, description="The context items usable at the end.")


#: A rebuild the person asked for, or a run that may open a discussion.
RunKind = Literal["rebuild", "opening"]


class RunSummary(DiscussionValue):
    """One producer run: its kind, its outcome, why, what it read and, once settled, its cost."""

    kind: RunKind = Field(description="A rebuild the person asked for, or an opening run.")
    state: RunState = Field(description="claimed while it runs, then its settled outcome.")
    claimed_at: AwareDatetime = Field(description="When the run started.")
    settled_at: AwareDatetime | None = Field(default=None, description="When it ended.")
    reason: RunReason | None = Field(default=None, description="Why it ended so, once settled.")
    stats: RunStats | None = Field(default=None, description="What it read and interpreted.")
    usage: RunUsage | None = Field(default=None, description="Its cost; none if nothing billed.")


#: The ceilings that can stop a run before it starts, in the order a run meets them:
#: the deployment's daily budget and the person's usage limit (asked by every model
#: call), then the discussions' own run, account-day and instance-day ceilings.
CeilingReached = Literal[
    "instance_budget", "usage_limit", "run_ceiling", "owner_day", "instance_day"
]


class BudgetState(DiscussionValue):
    """Whether a ceiling stops a run now: the first one a run would meet, never amounts."""

    configured: StrictBool = Field(description="All three operator ceilings are set.")
    reached: CeilingReached | None = Field(
        default=None, description="The first ceiling that stops a run now, or none."
    )
    resets_at: AwareDatetime | None = Field(
        default=None, description="When a reached day ceiling starts again (the UTC day's end)."
    )


#: Why a requested rebuild cannot start, when the cause is server-side: the person's
#: rules do not fit their budget, or a ceiling stops every run now.
RebuildObstacle = Literal["controls_over_budget", "ceiling_reached"]


class AwaitingReply(DiscussionValue):
    """An opening still awaiting the person's reply, which holds the next one back."""

    since: AwareDatetime = Field(description="When the opening was published.")
    until: AwareDatetime = Field(
        description="When it stops holding the next opening, unless the person answers first."
    )


class DiscussionActivity(DiscussionValue):
    """The producer's work as the settings page shows it, never inferred client-side."""

    rebuild: Literal["idle", "requested", "running"] = Field(
        description="A rebuild is running, waiting for a run to serve it, or not asked."
    )
    obstacle: RebuildObstacle | None = Field(
        default=None,
        description="Why a requested rebuild cannot start, when the cause is server-side.",
    )
    last_rebuild: RunSummary | None = Field(default=None, description="The latest rebuild run.")
    last_update: RunSummary | None = Field(
        default=None, description="The latest settled run that updated the context."
    )
    last_run: RunSummary | None = Field(
        default=None, description="The latest settled run, whatever its kind."
    )
    budget: BudgetState = Field(description="Whether a ceiling stops a run now.")
    awaiting_reply: AwaitingReply | None = Field(
        default=None,
        description="The opening awaiting a reply that holds the next one back now, if any.",
    )
