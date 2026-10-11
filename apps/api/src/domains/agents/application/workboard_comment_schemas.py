"""Literal comments pin the current ticket and expose the source answer consequences."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.workboard.answers import Answer
from src.domains.workboard.schemas import CommentCreate


class WorkboardCommentInput(CommentCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ticket_id: UUID


class WorkboardCommentSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: WorkboardCommentInput
    title: str
    owner_id: UUID
    status: str
    assignee_kind: str
    holder_id: UUID
    answer: Answer | None
    pending_preview: list[str]
    max_comment_chars: int = Field(ge=1)
    max_runs: int = Field(ge=1)
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {
            "ticket_id": str(self.request.ticket_id),
            "title": self.title,
            "owner_id": str(self.owner_id),
            "holder_id": str(self.holder_id),
            "body": self.request.body,
            "status": self.status,
            "answer": self.answer.value if self.answer else None,
            "pending_preview": list(self.pending_preview),
            "max_comment_chars": self.max_comment_chars,
            "max_runs": self.max_runs,
            "comment_requested": after,
            "resulting_status": (
                ("done" if self.answer == Answer.REFUSE else "todo")
                if self.answer and after
                else self.status
            ),
            "lia_may_run_later": after and self.answer in {Answer.APPROVE, Answer.AMEND},
            "pending_action_approved": after and self.answer == Answer.APPROVE,
        }


class WorkboardCommentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    workboard_comment: WorkboardCommentSelection


class WorkboardCommentField(StrEnum):
    COMMENT = "workboard_comment"


def canonical_workboard_comment(draft: ApplicationActionDraftContent) -> bool:
    scope = WorkboardCommentPatch.model_validate(draft.intent).workboard_comment
    return draft.before == {"workboard_comment": scope.public_scope()} and draft.after == {
        "workboard_comment": scope.public_scope(after=True)
    }
