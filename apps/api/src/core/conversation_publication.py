"""Explicit destinations for invocation results and independent Main notifications."""

from dataclasses import dataclass
from uuid import UUID

from src.core.conversation_execution import ReservedWork, RunAdmission


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
