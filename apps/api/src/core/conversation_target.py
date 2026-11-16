"""Dependency-free identity contract shared by domains and persistence adapters."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Self
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


@dataclass(frozen=True, slots=True)
class ConversationOrigin:
    """The discussion generation an act was begun in: its return comes back there.

    Stored beside the act, never trusted as a destination by itself: the
    publication checks that this generation still lives (not deleted, not
    reset since), and Main receives the return otherwise.
    """

    conversation_id: UUID
    revision: int

    @classmethod
    def of(cls, target: ConversationRef) -> Self:
        """The origin an act begun in ``target`` records."""
        return cls(target.id, target.revision)
