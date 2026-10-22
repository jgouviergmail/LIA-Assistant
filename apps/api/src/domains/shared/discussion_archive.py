"""A transaction-local archive port, independent of the chat graph and its engine."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class ArchivedDiscussion:
    """Where an archived opening landed: its conversation and its message."""

    conversation_id: UUID
    message_id: UUID


class DiscussionArchiveWriter(Protocol):
    """The port that archives one assistant message inside the caller's transaction."""

    async def __call__(
        self, db: AsyncSession, *, owner_id: UUID, content: str, metadata: dict[str, JsonValue]
    ) -> ArchivedDiscussion:
        """Archive one assistant message without committing or doing network IO."""
        ...
