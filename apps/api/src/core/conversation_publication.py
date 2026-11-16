"""Explicit destinations for invocation results and independent Main notifications."""

from dataclasses import dataclass
from uuid import UUID

from src.core.conversation_execution import ReservedWork, RunAdmission
from src.core.conversation_target import ConversationOrigin


@dataclass(frozen=True, slots=True)
class PinnedRunPublication:
    """A result belongs to the admitted generation, even when it arrives late."""

    admission: RunAdmission


@dataclass(frozen=True, slots=True)
class CurrentPrimaryPublication:
    """An independent notification resolves the account's current Main at publication."""

    owner_id: UUID


@dataclass(frozen=True, slots=True)
class PinnedReservationPublication:
    """A voice archive belongs to one still-running reservation contribution."""

    work: ReservedWork


@dataclass(frozen=True, slots=True)
class OriginPublication:
    """The return of an act goes to the generation it began in while it lives, else to Main."""

    owner_id: UUID
    origin: ConversationOrigin


def return_publication(
    owner_id: UUID, origin: ConversationOrigin | None
) -> OriginPublication | CurrentPrimaryPublication:
    """Where the return of an act publishes: its origin, or Main for work begun nowhere."""
    if origin is None:
        return CurrentPrimaryPublication(owner_id)
    return OriginPublication(owner_id, origin)


type PublicationDestination = (
    UUID
    | PinnedRunPublication
    | CurrentPrimaryPublication
    | PinnedReservationPublication
    | OriginPublication
)
