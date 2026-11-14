"""Public reconciliation coordinates; a stream never publishes its private authority."""

from src.core.conversation_execution import RunAdmission
from src.core.conversation_target import ConversationRef
from src.core.field_names import (
    FIELD_CONVERSATION_ID,
    FIELD_CONVERSATION_KIND,
    FIELD_CONVERSATION_REVISION,
    FIELD_RUN_ID,
    FIELD_STREAM_ID,
)
from src.domains.agents.api.schemas import ChatStreamChunk


def with_invocation_identity(chunk: ChatStreamChunk, admission: RunAdmission) -> ChatStreamChunk:
    """Copy without mutating collaborators' events; admitted coordinates always win."""
    return chunk.model_copy(
        update={
            "metadata": {
                **(chunk.metadata or {}),
                **stream_metadata(admission.target, admission.run_id, admission.stream_id),
            },
        }
    )


def stream_metadata(target: ConversationRef, run_id: str, stream_id: str) -> dict[str, str | int]:
    """Public coordinates shared by produced and transport-only terminal events."""
    return {
        FIELD_CONVERSATION_ID: str(target.id),
        FIELD_CONVERSATION_REVISION: target.revision,
        FIELD_CONVERSATION_KIND: target.kind.value,
        FIELD_RUN_ID: run_id,
        FIELD_STREAM_ID: stream_id,
    }
