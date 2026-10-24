"""A run's authority is a durable, versioned lease, never a local task flag."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt

from src.domains.shared.discussion_sources import DiscussionValue

RunState = Literal["claimed", "completed", "skipped", "failed", "abandoned"]
SettledRunState = Literal["completed", "skipped", "failed", "abandoned"]

#: How a context build ended. The first three mean something was understood or
#: reused; the last four mean nothing could be interpreted, and why —
#: ``rules_refused``: the compiled reading of the person's rules quoted words they
#: never wrote, so nothing was read.
ContextOutcome = Literal[
    "context_ready",
    "context_built",
    "unchanged",
    "no_source",
    "no_fact",
    "prompt_full",
    "rules_refused",
]
#: What the decision chose when the context was ready.
DecisionOutcome = Literal["published", "decision_skip", "decision_defer"]
#: The expected abstentions a run raises while it acts (``InitiativeStopped``).
StopReason = Literal[
    "attention_busy",
    "conversation_busy",
    "directives_changed",
    "duplicate_opening",
    "evidence_changed",
    "evidence_page_missing",
    "evidence_refused",
    "producer_disabled",
    "read_budget_exhausted",
    "stale_claim",
    "unreconciled_spend",
]
#: What holds the person's attention so that no opening run starts, in the order the
#: gate asks (``attention_hold``): a message they just wrote, an opening still awaiting
#: their reply, a recent alert, a recent opening, a reminder about to ring, a turn
#: streaming, an approval waiting.
AttentionHold = Literal[
    "recent_turn",
    "pending_opening",
    "recent_alert",
    "recent_opening",
    "reminder_due",
    "turn_streaming",
    "approval_pending",
]
#: Why the run's financial permit refused a call (``DiscretionaryBudgetRefused``).
SpendRefusal = Literal[
    "tariff_unavailable",
    "allowance_exhausted",
    "phase_exhausted",
    "day_over",
    "reservation_refused",
]
#: Why a run ended as it did: ONE closed vocabulary, stored on the run row, read by
#: the settings page (each member has its sentence, guarded) and by the logs.
RunReason = (
    ContextOutcome
    | DecisionOutcome
    | StopReason
    | SpendRefusal
    | Literal[
        "budget_exhausted",
        "run_ceiling_too_low",
        "usage_limit_reached",
        "controls_over_budget",
        "provider_backoff",
        "deadline_reached",
        "failed",
    ]
)


class RunClaim(DiscussionValue):
    """The durable authority of one run.

    A run may write only while the account's preference row still carries this
    run id, fence, policy revision and context epoch, and before the lease ends
    (``owns_claim``).
    """

    owner_id: UUID
    run_id: UUID
    fence: Annotated[StrictInt, Field(ge=1)]
    policy_revision: Annotated[StrictInt, Field(ge=0)]
    context_epoch: Annotated[StrictInt, Field(ge=0)]
    lease_until: AwareDatetime
