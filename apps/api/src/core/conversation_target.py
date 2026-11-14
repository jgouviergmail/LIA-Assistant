"""Dependency-free identity contract shared by domains and persistence adapters."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ConversationKind(StrEnum):
    """Business role of a discussion, independent of its title or selection."""

    MAIN = "main"
    SECONDARY = "secondary"


@dataclass(frozen=True, slots=True)
class ConversationRef:
    """A resolved owner, stable discussion and resettable runtime generation."""

    owner_id: UUID
    id: UUID
    kind: ConversationKind
    revision: int
    runtime_id: UUID
