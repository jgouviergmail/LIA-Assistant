"""Public execution status contains business coordinates, never private runtime authority."""

from uuid import UUID

from pydantic import BaseModel, Field

from src.core.conversation_execution import ExecutionPhase, RunBusy
from src.core.conversation_target import ConversationKind


class ActiveRunResponse(BaseModel):
    """Account-wide occupancy and the operations this invocation actually supports."""

    active: bool = Field(default=False, description="An invocation still occupies the account.")
    conversation_id: UUID | None = Field(default=None, description="Occupied business discussion.")
    conversation_revision: int | None = Field(default=None, description="Admitted generation.")
    conversation_kind: ConversationKind | None = Field(default=None, description="Discussion role.")
    title: str | None = Field(default=None, description="The owner's discussion title.")
    phase: ExecutionPhase | None = Field(default=None, description="Actual SQL lifecycle phase.")
    run_id: str | None = Field(default=None, description="Billing correlation.")
    stream_id: str | None = Field(default=None, description="Reconnectable stream, if provided.")
    can_resume: bool = Field(default=False, description="A running relay can be subscribed to.")
    can_cancel: bool = Field(
        default=False, description="This producer observes browser stop signals."
    )
    selected: bool = Field(
        default=False, description="The invocation targets the selected discussion."
    )

    @classmethod
    def occupied(
        cls, busy: RunBusy, title: str | None, *, selected: bool = False
    ) -> ActiveRunResponse:
        """Project one occupancy snapshot for HTTP 200 and HTTP 409 alike."""
        return cls(
            active=True,
            conversation_id=busy.target.id,
            conversation_revision=busy.target.revision,
            conversation_kind=busy.target.kind,
            title=title,
            phase=busy.phase,
            run_id=busy.run_id,
            stream_id=busy.stream_id,
            can_resume=busy.stream_id is not None and busy.phase == ExecutionPhase.RUNNING,
            can_cancel=busy.cancellable and busy.phase == ExecutionPhase.RUNNING,
            selected=selected,
        )


class CancelRunResponse(BaseModel):
    """Acknowledges a stop REQUEST, never completion or reversal of prior effects."""

    cancelled: bool = Field(description="The cancellation request was recorded.")
    stream_id: str | None = Field(default=None, description="The exact invocation asked to stop.")
