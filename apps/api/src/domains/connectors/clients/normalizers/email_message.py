"""The e-mail vocabulary every provider's normaliser must produce (ADR-287).

A CONTRACT, not a runtime layer: the normalisers keep returning the dicts the
tool layer, the cards and the context store already read, and this model says
which keys those dicts carry whatever the mailbox — Gmail, Microsoft Graph or
IMAP. The contract test validates each normaliser's output against it on a
real-shaped payload, so a fourth provider is one normaliser plus one golden.

Until 2026-09-15 the "unified format" was the Gmail format: Graph and IMAP
fabricated a ``payload.headers`` list to look like Gmail, the Graph body stayed
raw HTML and the IMAP body was flattened by a regex. The vocabulary is now the
flat, provider-neutral one; only Gmail still carries its native ``payload`` tree,
until ``build_emails_output`` drops it (ADR-286) — the ``extra="allow"`` below is
that tolerance and nothing else.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EmailAttachment(BaseModel):
    """One attachment as every provider describes it."""

    model_config = ConfigDict(extra="allow")

    filename: str = Field(default="", description="File name as sent.")
    mimeType: str = Field(default="", description="MIME type as sent.")
    size: int = Field(default=0, description="Size in bytes when the provider says it.")
    attachmentId: str | None = Field(
        default=None, description="Provider handle to download the part, when any."
    )


class EmailMessage(BaseModel):
    """A message as the tool layer reads it, whatever the provider."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str = Field(description="Provider message id (the id every tool takes).")
    threadId: str = Field(
        description="Provider thread id; the message id where threads do not exist."
    )
    labelIds: list[str] = Field(
        default_factory=list, description="Gmail-style labels, UNREAD included."
    )
    snippet: str = Field(default="", description="One-line preview, text only.")
    subject: str = Field(default="", description="Subject line.")
    from_: str = Field(default="", alias="from", description="Sender, RFC 5322 name-addr.")
    to: str = Field(default="", description="Recipients, comma-separated name-addrs.")
    cc: str = Field(default="", description="Carbon copies, comma-separated name-addrs.")
    date: str = Field(default="", description="Date header as sent.")
    rfc_message_id: str | None = Field(
        default=None,
        description="RFC 2822 Message-ID, for threading a reply, when the provider exposes it.",
    )
    internalDate: str | None = Field(default=None, description="Epoch milliseconds, as a string.")
    body: str = Field(default="", description="Clean text — never markup, never base64.")
    attachments: list[EmailAttachment] = Field(default_factory=list)
    provider: str = Field(alias="_provider", description="google | microsoft | apple.")


__all__ = ["EmailAttachment", "EmailMessage"]
