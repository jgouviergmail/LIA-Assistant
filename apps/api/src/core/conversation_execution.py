"""Immutable authority for one graph invocation or one reserved voice session."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from src.core.conversation_target import ConversationRef


class ExecutionKind(StrEnum):
    """A Live reservation protects its target without occupying the graph slot."""

    GRAPH = "graph"
    LIVE = "live"


class ExecutionPhase(StrEnum):
    """A stream ending or a heartbeat expiring is never proof of CLOSED."""

    RUNNING = "running"
    DRAINING = "draining"
    RECOVERING = "recovering"
    CLOSED = "closed"


class RunEnd(StrEnum):
    """How an invocation ended, declared by its driver and written at its close (ADR-384).

    An end nobody declared is not ``NORMAL``: a failure is never read as success.
    """

    NORMAL = "normal"
    INTERRUPTED = "interrupted"
    UNSTARTED = "unstarted"


ReservationPurpose = Literal["opening", "request", "closing", "relay"]


class ReservationWorkPhase(StrEnum):
    """Unknown work remains occupied until an explicit recovery proves its end."""

    RUNNING = "running"
    UNKNOWN = "unknown"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    """The private owner-bound invocation coordinate carried to native persistence."""

    activity_id: UUID
    worker_id: UUID
    owner_token: UUID
    fence: int


@dataclass(frozen=True, slots=True)
class RunAdmission:
    """Server-owned invocation authority; never accepted from an HTTP body."""

    activity_id: UUID
    target: ConversationRef
    kind: ExecutionKind
    run_id: str
    stream_id: str
    worker_id: UUID
    owner_token: UUID
    fence: int
    relayed: bool
    cancellable: bool = False

    @property
    def identity(self) -> ExecutionIdentity:
        """Project the private fence without duplicating business or billing state."""
        return ExecutionIdentity(self.activity_id, self.worker_id, self.owner_token, self.fence)


@dataclass(frozen=True, slots=True)
class RunBusy:
    """Owner-visible occupancy without the producer's private authority token."""

    target: ConversationRef
    kind: ExecutionKind
    phase: ExecutionPhase
    run_id: str
    stream_id: str | None
    cancellable: bool = False


@dataclass(frozen=True, slots=True)
class ReservedWork:
    """One actual worker's contribution to a durable voice reservation."""

    admission: RunAdmission
    id: UUID
    worker_id: UUID
    owner_token: UUID
    purpose: ReservationPurpose


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    """Detached SQL liveness facts; neither heartbeat age nor transport grants authority."""

    busy: RunBusy
    stream_id: str
    relayed: bool
    heartbeat_at: datetime
    title: str | None


class ExecutionRevoked(RuntimeError):
    """The invocation no longer has authority to start work or write runtime state."""

    def __init__(self) -> None:
        super().__init__("Conversation execution authority is no longer current")


class ConversationBusy(RuntimeError):
    """A caller maps occupied admission to its own HTTP or runner vocabulary."""

    def __init__(self, busy: RunBusy) -> None:
        self.busy = busy
        super().__init__("An execution already occupies this account")
