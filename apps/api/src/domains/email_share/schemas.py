"""The wire shapes of sending a file or an answer by e-mail (ADR-321)."""

from __future__ import annotations

import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.core.constants import (
    EMAIL_SHARE_MARKDOWN_MAX_CHARS,
    EMAIL_SHARE_MAX_RECIPIENTS,
    EMAIL_SHARE_MESSAGE_MAX_CHARS,
    EMAIL_SHARE_SUBJECT_MAX_CHARS,
)

#: Where a message leaves from: the person's own mailbox, or LIA's relay to
#: their own verified address.
ShareRouteKind = Literal["mailbox", "relay"]


class SharedFile(BaseModel):
    """One of the person's generated files (an image, a document, a capture)."""

    kind: Literal["file"] = Field(description="A stored file LIA generated.")
    attachment_id: UUID = Field(description="The file, as the gallery and the chat cards name it.")


class SharedMarkdown(BaseModel):
    """An answer, as the ``.md`` file « Download » writes (built by the caller)."""

    kind: Literal["markdown"] = Field(description="An answer, as its Markdown export.")
    filename: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$",
        description="The file's name without its extension; `.md` is added.",
    )
    text: str = Field(
        min_length=1,
        max_length=EMAIL_SHARE_MARKDOWN_MAX_CHARS,
        description="The Markdown, exactly as « Download » would write it.",
    )

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("an answer with no text cannot be sent")
        return value


class EmailShareRequest(BaseModel):
    """Send one file or one answer, with a subject and optional words."""

    recipients: list[EmailStr] = Field(
        default_factory=list,
        max_length=EMAIL_SHARE_MAX_RECIPIENTS,
        description=(
            "Who receives it — through the person's own mailbox. Without one, LIA's "
            "relay only writes to the account's verified address and this stays empty."
        ),
    )
    subject: str = Field(
        min_length=1,
        max_length=EMAIL_SHARE_SUBJECT_MAX_CHARS,
        description="The e-mail's subject, one line.",
    )
    message: str | None = Field(
        default=None,
        max_length=EMAIL_SHARE_MESSAGE_MAX_CHARS,
        description="The words above the file; nothing is written in their place.",
    )
    attachment: Annotated[SharedFile | SharedMarkdown, Field(discriminator="kind")] = Field(
        description="What is sent: a generated file, or an answer as Markdown."
    )

    @field_validator("subject")
    @classmethod
    def _one_line(cls, value: str) -> str:
        # A line break in a header is how a header is forged; every control
        # character is refused with it.
        if any(unicodedata.category(char) == "Cc" for char in value):
            raise ValueError("the subject must be one line of text")
        stripped = value.strip()
        if not stripped:
            raise ValueError("the subject cannot be blank")
        return stripped

    @field_validator("message")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class EmailShareOptions(BaseModel):
    """What the « Send by e-mail » dialog may offer this account, right now."""

    model_config = ConfigDict(frozen=True)

    route: ShareRouteKind | Literal["unavailable"] = Field(
        description=(
            "`mailbox`: free recipients, through the connected mailbox. `relay`: the "
            "account's own verified address only. `unavailable`: neither."
        )
    )
    own_address: str | None = Field(
        description="The one recipient of the relay route (the account's verified address)."
    )
    mailbox_needs_reconnect: bool = Field(
        description="A mailbox is connected but broken: it must be reconnected to be used."
    )
    max_file_bytes: int | None = Field(
        description="The largest file this route carries, derived from its provider."
    )
    max_recipients: int = Field(description="The published recipient cap.")
    subject_max_chars: int = Field(description="The published subject length cap.")
    message_max_chars: int = Field(description="The published message length cap.")


class EmailShareResult(BaseModel):
    """What a send did."""

    model_config = ConfigDict(frozen=True)

    route: ShareRouteKind = Field(description="Where the message left from.")
    recipients: int = Field(description="How many addresses it was sent to.")
