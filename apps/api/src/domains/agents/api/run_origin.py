"""What an out-of-turn run is, published to the turn it drives (ADR-276).

``AgentService.stream_chat_response`` sits nine logical lines under its frozen
size cap, so a run cannot hand it a parameter. It publishes a ContextVar
instead — the shape ``capability_directive_ctx`` already uses — and two readers
consult it:

- the archive enrichers, which mark both rows of the run ``hidden`` so the chat
  stays quiet while the RECORD stays whole. Archiving nothing was the first
  design and it was wrong: the decision register (ADR-263, lot 6) POINTS at the
  request and the answer with ``SET NULL`` tombstones, so a run with no rows
  would have been indistinguishable from a deleted conversation;
- the effect gate, which records the refusals it issues, so a run's settle
  reads a stable CODE and never the model's prose.

Two properties are load-bearing and easy to lose:

- **the refusals are collected through the SHARED object**, never by setting the
  ContextVar again. A ``set()`` inside a child task does not reach its parent —
  the very trap ADR-263 lot 4 paid for with the consultation register, which
  worked in ReAct and silently lost every pipeline turn;
- **the stamp returns a new dict.** One turn's metadata must never leak into
  another's, the rule every enricher in this package follows.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from src.core.field_names import FIELD_HIDDEN


@dataclass(frozen=True)
class ApprovedDraft:
    """The action the person approved on their ticket, by IDENTITY (lot 7).

    Attributes:
        draft_type: The draft family the approval was given for.
        digest: ``drafts_digest`` of what they were shown — one draft, or a
            whole batch in order. What runs unattended must be what was
            displayed (ADR-092), so the replay is let through on this identity
            and on nothing looser: a different recipient, body or amount asks
            again, and so does a batch with one more item.
    """

    draft_type: str
    digest: str

    def matches(self, draft_type: str, digest: str) -> bool:
        """Whether a rebuilt draft is the approved one.

        Args:
            draft_type: The rebuilt draft's family.
            digest: ``draft_digest`` of its content.

        Returns:
            True on the exact identity only.
        """
        return self.draft_type == draft_type and self.digest == digest


@dataclass
class RunOrigin:
    """The out-of-turn run driving the current turn.

    Attributes:
        kind: Which surface started it — ``workboard`` today. It is also the
            metadata key the stamp writes under, so it stays a bounded word.
        ticket_id: What the run is about, as a string: this becomes a metadata
            value, and metadata is JSON.
        run_id: The turn's own id, shared with the three ADR-263 registers.
        refusals: ``(tool_name, error_code)`` the gate refused, in order.
        can_carry_draft: True when the surface can put a draft in front of the
            person and wait for their answer (a ticket can; a routine cannot).
            The effect gate lets such a run BUILD the confirmation the chat
            would have shown instead of refusing it (lot 7).
        approved_draft: The action the person approved on the ticket, when the
            run is its replay. Spent by :func:`consume_approved_draft` on the
            first draft that matches it.
    """

    kind: str
    ticket_id: str
    run_id: str
    refusals: list[tuple[str, str]] = field(default_factory=list)
    can_carry_draft: bool = False
    approved_draft: ApprovedDraft | None = None


out_of_turn_origin_ctx: ContextVar[RunOrigin | None] = ContextVar(
    "out_of_turn_origin", default=None
)


def current_origin() -> RunOrigin | None:
    """The run driving this turn.

    Returns:
        The origin, or None inside an ordinary chat turn.
    """
    return out_of_turn_origin_ctx.get()


def current_origin_carries_drafts() -> bool:
    """Whether the run driving this turn can carry a draft to the person.

    Returns:
        True inside a workboard run; False in a routine and in the chat.
    """
    origin = out_of_turn_origin_ctx.get()
    return origin is not None and origin.can_carry_draft


def consume_approved_draft(draft_type: str, digest: str) -> bool | None:
    """Spend the approval the run carries, if it is for THIS draft.

    Reads and mutates the SHARED origin object, never the ContextVar: a node
    runs in a copy of the context, and spending the approval there must be
    seen by the next node of the same turn.

    Args:
        draft_type: The rebuilt draft's family.
        digest: ``draft_digest`` of its content.

    Returns:
        None when the run carries no approval (every ordinary turn); True when
        the draft is the approved one — the approval is SPENT, so a second
        identical draft in the same run asks again; False when the run carries
        an approval for something else.
    """
    origin = out_of_turn_origin_ctx.get()
    if origin is None or origin.approved_draft is None:
        return None
    if origin.approved_draft.matches(draft_type, digest):
        origin.approved_draft = None
        return True
    return False


def record_refusal(tool_name: str, error_code: str) -> None:
    """Note that the gate refused a capability, for the run's settle to read.

    Best-effort by contract: outside a run there is nothing to record, and this
    must never cost a turn its answer.

    Args:
        tool_name: The capability that was refused.
        error_code: The gate's stable error code.
    """
    origin = out_of_turn_origin_ctx.get()
    if origin is not None:
        origin.refusals.append((tool_name, error_code))


def with_hidden_stamp(metadata: dict[str, Any]) -> dict[str, Any]:
    """Mark an archived row as belonging to an out-of-turn run.

    Args:
        metadata: What the caller assembled.

    Returns:
        A NEW dict carrying the stamp when a run is driving; the caller's own
        object, untouched, when none is.
    """
    origin = out_of_turn_origin_ctx.get()
    if origin is None:
        return metadata
    return {
        **metadata,
        FIELD_HIDDEN: True,
        origin.kind: {"ticket_id": origin.ticket_id, "run_id": origin.run_id},
    }
