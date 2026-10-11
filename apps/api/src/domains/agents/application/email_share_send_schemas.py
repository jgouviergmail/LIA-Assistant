"""Literal email envelope and exact existing-account sources; private witnesses stay server-owned."""

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.email_share.schemas import EmailShareEnvelope, EmailShareRequest, SharedFile


class NativeSharedFile(SharedFile):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SharedSavedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["saved_answer"]
    bookmark_id: UUID


class SharedArchivedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["answer"]
    message_id: UUID


class EmailShareSendInput(EmailShareEnvelope):
    model_config = ConfigDict(extra="forbid", frozen=True)
    attachment: Annotated[
        NativeSharedFile | SharedSavedAnswer | SharedArchivedAnswer, Field(discriminator="kind")
    ]


assert set(EmailShareSendInput.model_fields) == set(EmailShareRequest.model_fields)


class EmailShareSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: EmailShareSendInput
    route: Literal["mailbox", "relay"]
    connector_type: str | None
    recipients: tuple[str, ...]
    filename: str
    file_bytes: StrictInt = Field(ge=0)
    content_type: str
    answer_preview: str | None = None
    state_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)

    def public_scope(self, *, after: bool = False) -> dict[str, JsonValue]:
        return {**self.model_dump(mode="json", exclude={"state_digest"}), "send_requested": after}


class EmailShareSendPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    email_to_send: EmailShareSnapshot


class EmailShareSendField(StrEnum):
    SEND = "email_to_send"


def canonical_email_share(draft: ApplicationActionDraftContent) -> bool:
    scope = EmailShareSendPatch.model_validate(draft.intent).email_to_send
    return draft.before == {"email_to_send": scope.public_scope()} and draft.after == {
        "email_to_send": scope.public_scope(after=True)
    }
