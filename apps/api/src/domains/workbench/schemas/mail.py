"""What the mail routes take and answer — folders and labels (ADR-369, Task 4.1).

A folder is a SYSTEM place (its role names it; the page translates the role)
or one of the person's own (its name is theirs). Its ``id`` is what the
listing route takes back: ``system:<role>``, or the provider's handle of the
person's folder (a Gmail label id; a folder name elsewhere). Gmail's labels
ARE its user folders — the label manager reads the pane, not a route of its
own. An application names at least one label and stays within the published
bulk bound.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.domains.workbench.ids import (
    OptionalPageToken,
    OptionalProviderId,
    OptionalProviderName,
    ProviderId,
    ProviderName,
)

#: The system places of a mailbox, in the order the pane draws them.
MailRole = Literal["inbox", "starred", "sent", "drafts", "archive", "spam", "trash"]
#: The prefix of a system place's id (a provider handle never starts with it:
#: a Gmail label id is ``Label_…``, a folder name has no colon).
SYSTEM_FOLDER_PREFIX: Final = "system:"

#: How many labels one application may name on each side. The page applies one
#: label per click, so it never meets this bound: it only stops a crafted body.
LABELS_PER_APPLICATION_MAX: Final = 50

_LabelIds = Annotated[list[ProviderId], Field(max_length=LABELS_PER_APPLICATION_MAX)]


class MailFolder(BaseModel):
    """One place of the mailbox."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="What the listing takes back (``system:<role>`` or a handle).")
    kind: Literal["system", "user"] = Field(description="A system place or the person's own.")
    role: MailRole | None = Field(description="A system place's role; None for the person's.")
    name: str | None = Field(description="The person's folder's name; None for a system place.")


class MailFolders(BaseModel):
    """The folder pane."""

    folders: list[MailFolder] = Field(description="System places first, then the person's own.")


class NewLabel(BaseModel):
    """A label to create."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[ProviderName, StringConstraints(strip_whitespace=True)] = Field(
        description="Its name; « / » nests it under another."
    )


class LabelChange(BaseModel):
    """A label renamed."""

    model_config = ConfigDict(extra="forbid")

    label_id: ProviderId = Field(description="The label.")
    name: Annotated[ProviderName, StringConstraints(strip_whitespace=True)] = Field(
        description="Its new name."
    )


class MessageSelection(BaseModel):
    """The messages one act is about: one at least, the published bulk bound at most."""

    model_config = ConfigDict(extra="forbid")

    message_ids: list[ProviderId] = Field(
        min_length=1,
        max_length=settings.workbench_bulk_max_items,
        description="The selection (at most the published bulk bound).",
    )


class ReadStateChange(MessageSelection):
    """A selection marked read or unread."""

    read: bool = Field(description="True marks them read, False unread.")


class LabelApplication(MessageSelection):
    """Labels added to and removed from a selection, in one act."""

    add: _LabelIds = Field(default_factory=list, description="Labels to add.")
    remove: _LabelIds = Field(default_factory=list, description="Labels to remove.")

    @model_validator(mode="after")
    def _changes_something(self) -> Self:
        if not self.add and not self.remove:
            raise ValueError("an application adds or removes at least one label")
        if set(self.add) & set(self.remove):
            raise ValueError("a label is either added or removed, never both")
        return self


#: The person's words in a search box: bounded, no control character.
_SearchWords = Annotated[
    str | None,
    StringConstraints(max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS, pattern=r"^[^\x00-\x1f\x7f]*$"),
]


class MailListing(BaseModel):
    """What one page of a listing reads: a folder, the person's words, the chips."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    folder: ProviderName = Field(
        default=f"{SYSTEM_FOLDER_PREFIX}inbox",
        description="A folder of the pane: ``system:<role>``, a Gmail label id or a folder name.",
    )
    q: _SearchWords = Field(
        default=None, description="The person's words, in the Gmail-style search syntax."
    )
    unread: bool = Field(default=False, description="Unread messages only.")
    attachments: bool = Field(
        default=False, description="Messages with an attachment only (where offered)."
    )
    after: date | None = Field(default=None, description="The first day included.")
    before: date | None = Field(default=None, description="The first day NOT included.")
    page_token: OptionalPageToken = Field(default=None, description="The next page's token.")

    @model_validator(mode="after")
    def _a_range_ends_after_it_starts(self) -> Self:
        if self.after is not None and self.before is not None and self.before <= self.after:
            raise ValueError("a date range ends after it starts")
        return self


class MailAddress(BaseModel):
    """One mailbox of a header, read apart."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="The display name; empty when none was sent.")
    address: str = Field(description="The address as sent.")


class MailSummary(BaseModel):
    """One row of a listing (headers only)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The message's id.")
    thread_id: str = Field(description="Its conversation's id (its own id where none exist).")
    sender: MailAddress | None = Field(description="Who sent it, when the header says.")
    subject: str = Field(description="Its subject.")
    snippet: str = Field(description="A one-line preview, text only.")
    received_at: datetime | None = Field(description="When the mailbox received it (UTC).")
    is_read: bool = Field(description="Whether it was read.")
    is_starred: bool = Field(description="Whether it is starred (flagged).")
    label_ids: list[str] = Field(
        description="The person's own Gmail labels on it (ids); none elsewhere."
    )


class MailPage(BaseModel):
    """One page of a listing."""

    items: list[MailSummary] = Field(description="The page, in the mailbox's order.")
    next_page_token: str | None = Field(description="The next page's token; None at the end.")
    skipped: int = Field(
        ge=0, description="Hits the provider listed but could not read: the page is partial."
    )


class MailAttachment(BaseModel):
    """One attachment of a message."""

    model_config = ConfigDict(frozen=True)

    id: str | None = Field(
        description="The provider's handle (Gmail's may expire: the name travels with it)."
    )
    filename: str = Field(description="Its name as sent.")
    mime_type: str = Field(description="Its type as sent.")
    size: int | None = Field(description="Its size in bytes, when the provider says.")


class MailMessage(BaseModel):
    """One message, as the reader draws it. Reading it marks nothing read."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The message's id.")
    thread_id: str = Field(description="Its conversation's id.")
    sender: MailAddress | None = Field(description="Who sent it.")
    reply_to: list[MailAddress] = Field(description="Where a reply goes, when not the sender.")
    to: list[MailAddress] = Field(description="Its recipients.")
    cc: list[MailAddress] = Field(description="Its copies.")
    subject: str = Field(description="Its subject.")
    received_at: datetime | None = Field(description="When the mailbox received it (UTC).")
    is_read: bool = Field(description="Whether it was read.")
    is_starred: bool = Field(description="Whether it is starred (flagged).")
    label_ids: list[str] = Field(
        description="The person's own Gmail labels on it (ids); none elsewhere."
    )
    body: str = Field(description="Its text, the quoted history left out.")
    attachments: list[MailAttachment] = Field(description="Its attachments.")


class MailHtml(BaseModel):
    """A message as its author laid it out (D3) — drawn only in a sandboxed frame."""

    model_config = ConfigDict(frozen=True)

    html: str | None = Field(
        description="Its HTML body; null when it has none (the text reader shows instead)."
    )
    truncated: bool = Field(
        description="Whether the HTML was cut at the published ceiling (workbench_mail_html_max_bytes)."
    )


class AttachmentRequest(BaseModel):
    """One attachment to download: its message, and its handle or its name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    message_id: ProviderId = Field(description="The message carrying it.")
    attachment_id: OptionalProviderId = Field(
        default=None, description="Its handle, as the reader listed it."
    )
    filename: OptionalProviderName = Field(
        default=None, description="Its name — what finds it when a Gmail handle expired."
    )

    @model_validator(mode="after")
    def _names_a_part(self) -> Self:
        if self.attachment_id is None and self.filename is None:
            raise ValueError("an attachment is named by its handle or its name")
        return self
