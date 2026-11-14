"""Content-free lifecycle identities and explicit cleanup outcomes."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.core.conversation_target import ConversationRef


class ConversationAction(StrEnum):
    """A request identity includes the requested destructive act."""

    RESET = "reset"
    DELETE = "delete"


class CleanupState(StrEnum):
    """Only explicit completion of every phase produces SUCCEEDED."""

    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    NEEDS_ATTENTION = "needs_attention"
    SUCCEEDED = "succeeded"


class CleanupPhase(StrEnum):
    """Ordered idempotent phases; the stored phase is the next work to attempt."""

    CHECKPOINT = "checkpoint"
    CONTEXT = "context"
    PENDING = "pending"
    FILES = "files"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class CleanupClaim:
    """Detached immutable target and revocable authority for one cleanup attempt."""

    operation_id: UUID
    target: ConversationRef
    owner_token: UUID
    fence: int
    phase: CleanupPhase
    attachment_ids: tuple[UUID, ...]


class RuntimeCleanupPort(Protocol):
    """Native runtime adapters return an explicit result, never inferred success."""

    async def prepare_owner(self, owner: UUID) -> None:
        """Bind legacy Live occupancy before any source is retired, with no SQL transaction held."""
        ...

    async def purge_checkpoint(self, target: ConversationRef) -> bool:
        """Remove only this retired runtime's native checkpoint thread."""
        ...

    async def purge_tool_context(self, target: ConversationRef) -> bool:
        """Remove only this retired runtime's root and child Store namespaces."""
        ...

    async def purge_pending(self, target: ConversationRef) -> bool:
        """Revoke and purge only this runtime's declared transient inventory."""
        ...
