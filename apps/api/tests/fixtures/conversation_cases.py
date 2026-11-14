"""Strict conversation targets for tests of account, business and runtime identity."""

from uuid import UUID, uuid4

from src.core.conversation_target import ConversationKind, ConversationRef


def conversation_target(
    owner_id: UUID,
    conversation_id: UUID,
    *,
    kind: ConversationKind = ConversationKind.MAIN,
    revision: int = 0,
    runtime_id: UUID | None = None,
) -> ConversationRef:
    """Build an explicit migrated target, or a deliberately rotated generation."""
    return ConversationRef(owner_id, conversation_id, kind, revision, runtime_id or conversation_id)


def streaming_target(conversation_id: UUID) -> ConversationRef:
    """Unit stream formatting keeps a supplied public id and a distinct working runtime."""
    return conversation_target(uuid4(), conversation_id, runtime_id=uuid4())
