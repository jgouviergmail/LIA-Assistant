"""What the mail routes take and answer — writing (ADR-369, Task 4.5).

A recipient is ONE address as the person typed it — bare or ``Name <address>``,
one per chip — so a refusal can name its field and its place. A submission
that sends carries the page's key for that submission (one key per open
composer): it leaves once, whatever is clicked twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.config import settings
from src.core.constants import (
    WORKBENCH_MAIL_ATTACHMENTS_MAX,
    WORKBENCH_MAIL_BODY_MAX_CHARS,
    WORKBENCH_MAIL_RECIPIENT_MAX_CHARS,
    WORKBENCH_MAIL_RECIPIENTS_MAX,
    WORKBENCH_MAIL_SUBJECT_MAX_CHARS,
)
from src.domains.workbench.ids import OptionalProviderId, ProviderId
from src.domains.workbench.schemas.mail import MailAddress, MailAttachment

#: One recipient as typed: one line, bounded.
RecipientText = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=WORKBENCH_MAIL_RECIPIENT_MAX_CHARS,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
OptionalRecipientText = Annotated[
    str | None,
    StringConstraints(
        min_length=1,
        max_length=WORKBENCH_MAIL_RECIPIENT_MAX_CHARS,
        pattern=r"^[^\x00-\x1f\x7f]+$",
    ),
]
_Recipients = Annotated[list[RecipientText], Field(max_length=WORKBENCH_MAIL_RECIPIENTS_MAX)]
#: A subject: one line.
_SUBJECT: Final = StringConstraints(
    max_length=WORKBENCH_MAIL_SUBJECT_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]*$"
)
Subject = Annotated[str, _SUBJECT]
OptionalSubject = Annotated[str | None, _SUBJECT]
#: A body: lines and tabs, never a NUL.
_BODY: Final = StringConstraints(max_length=WORKBENCH_MAIL_BODY_MAX_CHARS, pattern=r"^[^\x00]*$")
Body = Annotated[str, _BODY]
OptionalBody = Annotated[str | None, _BODY]


#: A file a draft holds, as its reader showed it.
_HeldFileName = Annotated[str, StringConstraints(min_length=1, max_length=255)]
#: A recipient field of a change: absent keeps it, [] clears it.
_ChangedRecipients = Annotated[
    list[RecipientText] | None, Field(max_length=WORKBENCH_MAIL_RECIPIENTS_MAX)
]


class _Outgoing(BaseModel):
    """What a message carries beyond its words, counted together, and where it leaves from."""

    send_as: OptionalRecipientText = Field(
        default=None, description="The alias it leaves from; none: the mailbox's default."
    )
    html: OptionalBody = Field(
        default=None, description="Its words with their formatting; none: they are plain text."
    )
    attachment_ids: Annotated[list[UUID], Field(max_length=WORKBENCH_MAIL_ATTACHMENTS_MAX)] = Field(
        default_factory=list, description="The person's own files it carries."
    )
    drive_file_ids: Annotated[
        list[ProviderId], Field(max_length=WORKBENCH_MAIL_ATTACHMENTS_MAX)
    ] = Field(default_factory=list, description="Files of the person's drive it carries.")

    @model_validator(mode="after")
    def _files_are_bounded(self) -> Self:
        if len(self.attachment_ids) + len(self.drive_file_ids) > WORKBENCH_MAIL_ATTACHMENTS_MAX:
            raise ValueError("a message carries a bounded number of files")
        return self


class NewMessage(_Outgoing):
    """A new message, sent when the person presses « Send »."""

    model_config = ConfigDict(extra="forbid")

    to: _Recipients = Field(default_factory=list, description="Its recipients.")
    cc: _Recipients = Field(default_factory=list, description="Its copies.")
    bcc: _Recipients = Field(default_factory=list, description="Its blind copies.")
    subject: Subject = Field(default="", description="Its subject.")
    body: Body = Field(default="", description="Its text.")
    idempotency_key: UUID = Field(description="The page's key for this submission.")

    @model_validator(mode="after")
    def _reaches_someone(self) -> Self:
        if not (self.to or self.cc or self.bcc):
            raise ValueError("a message is addressed to someone")
        return self


class Reply(_Outgoing):
    """A reply to a message (its thread, its subject), sent at once.

    Recipients left out are the provider's to compute; those the person saw are
    what leaves, the person's own answer to who it reaches.
    """

    model_config = ConfigDict(extra="forbid")

    message_id: ProviderId = Field(description="The message answered.")
    body: Body = Field(description="The reply's text.")
    reply_all: bool = Field(default=False, description="Answer every recipient too.")
    to: _ChangedRecipients = Field(default=None, description="Its recipients, as chosen.")
    cc: _ChangedRecipients = Field(default=None, description="Its copies, as chosen.")
    idempotency_key: UUID = Field(description="The page's key for this submission.")

    @model_validator(mode="after")
    def _still_reaches_someone(self) -> Self:
        if self.to is not None and not self.to:
            raise ValueError("a reply whose recipients were chosen goes to someone")
        return self


class ReplyRecipients(BaseModel):
    """Who an answer would reach, for the person to change before it leaves."""

    model_config = ConfigDict(frozen=True)

    to: list[MailAddress] = Field(description="Its recipients.")
    cc: list[MailAddress] = Field(description="Its copies.")


class Forward(_Outgoing):
    """A message forwarded with its files, sent at once."""

    model_config = ConfigDict(extra="forbid")

    message_id: ProviderId = Field(description="The message forwarded.")
    to: Annotated[
        list[RecipientText], Field(min_length=1, max_length=WORKBENCH_MAIL_RECIPIENTS_MAX)
    ]
    cc: _Recipients = Field(default_factory=list, description="Its copies.")
    body: Body = Field(default="", description="A note above the forwarded message.")
    idempotency_key: UUID = Field(description="The page's key for this submission.")


class SentMessage(BaseModel):
    """What the provider says of a message that left."""

    model_config = ConfigDict(frozen=True)

    id: str | None = Field(description="The sent message's id, when the provider names it.")
    thread_id: str | None = Field(description="Its conversation's id, when named.")


class DraftSave(_Outgoing):
    """A draft created (no ``draft_id``) or changed (a field left out is kept).

    The files named join it; those it already holds stay until ``removed_files`` says
    otherwise, by name, the one handle that lasts on every provider.
    """

    model_config = ConfigDict(extra="forbid")

    draft_id: OptionalProviderId = Field(default=None, description="The draft changed.")
    expected_revision: OptionalProviderId = Field(
        default=None, description="The revision the editor holds (required for a change)."
    )
    to: _ChangedRecipients = Field(default=None, description="Its recipients.")
    cc: _ChangedRecipients = Field(default=None, description="Its copies.")
    bcc: _ChangedRecipients = Field(default=None, description="Its blind copies.")
    subject: OptionalSubject = Field(default=None, description="Its subject.")
    body: OptionalBody = Field(default=None, description="Its whole text.")
    removed_files: Annotated[
        list[_HeldFileName], Field(max_length=WORKBENCH_MAIL_ATTACHMENTS_MAX)
    ] = Field(default_factory=list, description="The names of files it no longer carries.")
    idempotency_key: UUID | None = Field(
        default=None, description="The page's key for a creation (required for one)."
    )

    @model_validator(mode="after")
    def _a_change_or_a_creation(self) -> Self:
        if self.draft_id is not None and self.expected_revision is None:
            raise ValueError("a change names the revision the editor holds")
        if self.draft_id is None and self.idempotency_key is None:
            raise ValueError("a creation carries the page's key for it")
        return self


class DraftSelection(BaseModel):
    """The drafts one act is about: one at least, the published bulk bound at most."""

    model_config = ConfigDict(extra="forbid")

    draft_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The drafts (at most the published bulk bound).",
    )


class DraftSend(BaseModel):
    """A draft sent as the editor last saw it."""

    model_config = ConfigDict(extra="forbid")

    draft_id: ProviderId = Field(description="The draft.")
    expected_revision: ProviderId = Field(description="The revision the person saw.")
    idempotency_key: UUID = Field(description="The page's key for this submission.")


class DraftSummary(BaseModel):
    """One row of the drafts listing."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The draft's id (iCloud gives a new one on every save).")
    to: list[MailAddress] = Field(description="Whom it is addressed to so far.")
    subject: str = Field(description="Its subject.")
    snippet: str = Field(description="A one-line preview.")
    updated_at: datetime | None = Field(description="When it was last saved (UTC).")


class DraftsPage(BaseModel):
    """One page of the drafts, newest first."""

    items: list[DraftSummary] = Field(description="The page.")
    next_page_token: str | None = Field(description="The next page's token; None at the end.")


class AttachableFile(BaseModel):
    """One of the person's own files a message may carry."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(description="The file.")
    filename: str = Field(description="Its name (its title when LIA gave it one).")
    mime_type: str = Field(description="Its type.")
    size: int = Field(description="Its size in bytes.")
    origin: str = Field(description="Uploaded by the person, or produced by LIA for them.")
    expires_at: datetime | None = Field(description="When it goes; None when kept.")


class AttachablePage(BaseModel):
    """One page of the files a message may carry, and their exact total."""

    items: list[AttachableFile] = Field(description="Newest first.")
    total: int = Field(ge=0, description="Every file the search matches, not the page.")
    next_offset: int | None = Field(description="Where the next page starts; None at the end.")


class MailDraft(BaseModel):
    """One draft, whole, with the revision an edit or a send is made against."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The draft's id.")
    revision: str = Field(description="Its stored revision.")
    sender: MailAddress | None = Field(description="Where it leaves from, when it says.")
    to: list[MailAddress] = Field(description="Its recipients.")
    cc: list[MailAddress] = Field(description="Its copies.")
    bcc: list[MailAddress] = Field(description="Its blind copies.")
    subject: str = Field(description="Its subject.")
    body: str = Field(description="Its whole text, the quoted message included.")
    attachments: list[MailAttachment] = Field(description="Its files.")
    updated_at: datetime | None = Field(description="When it was last saved (UTC).")
