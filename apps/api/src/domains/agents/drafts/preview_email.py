"""What an e-mail's confirmation card shows: beside the renderer, at its size cap.

A send, a reply, a forward and a delete share one description of an e-mail. A reply
says FIRST when the person already answered the message it answers (ADR-379): a second
answer is their right, never a blind one.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.drafts.card_spec import PreviewLine
from src.domains.agents.drafts.preview_rows import FormatDt, block, note, row


def render_email_send(
    content: dict[str, Any], lbl: dict[str, str], format_dt: FormatDt
) -> list[PreviewLine]:
    """Render email send/reply previews (to, cc, bcc, subject, body)."""
    lines: list[PreviewLine] = []
    to = content.get("to", "")
    cc = content.get("cc", "")
    bcc = content.get("bcc", "")
    subject = content.get("subject", "")
    # `or ""`: a body explicitly stored as None (forward without an added
    # message) must render empty, not as the literal string "None".
    body = content.get("body") or ""

    files = content.get("files") or []

    # Every field is optional to SHOW: a draft the model left half-filled is
    # still confirmed on what it holds, not on « Destinataire : » over nothing.
    if to:
        lines.append(row(lbl, "to", to))
    if cc:
        lines.append(row(lbl, "cc", cc))
    if bcc:
        lines.append(row(lbl, "bcc", bcc))
    if subject:
        lines.append(row(lbl, "subject", subject))
    # Before the message: the body is a block that ends the preview, and a list item
    # following it would open a second list under the words being approved.
    if files:
        names = [item.get("filename", item.get("name", "?")) for item in files]
        lines.append(row(lbl, "attachments", ", ".join(names)))
    if body:
        lines.append(block(lbl, "body", body))
    return lines


def render_email_reply(
    content: dict[str, Any], lbl: dict[str, str], format_dt: FormatDt
) -> list[PreviewLine]:
    """Render a reply preview: that the message was already answered is said first."""
    lines = render_email_send(content, lbl, format_dt)
    if not content.get("already_answered"):
        return lines
    answered_at = content.get("answered_at")
    said: PreviewLine = (
        row(lbl, "already_answered", format_dt(answered_at))
        if answered_at
        else note(lbl["already_answered"])
    )
    return [said, *lines]


def render_email_forward(
    content: dict[str, Any], lbl: dict[str, str], format_dt: FormatDt
) -> list[PreviewLine]:
    """Render an email forward preview: the original's files, then the person's."""
    files = [*(content.get("attachments") or []), *(content.get("files") or [])]
    return render_email_send({**content, "files": files}, lbl, format_dt)


def render_email_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: FormatDt
) -> list[PreviewLine]:
    """Render an email delete preview (sender, subject, date)."""
    # The stored subject is the raw truth ("" when the email has none); the
    # localized fallback is applied here, at render time.
    subject = content.get("subject") or lbl["no_subject"]
    from_addr = content.get("from", content.get("from_addr", "?"))
    date_raw = content.get("date", "")
    date = format_dt(date_raw) if date_raw else ""

    lines: list[PreviewLine] = [
        row(lbl, "from", from_addr),
        row(lbl, "subject", subject),
    ]
    if date:
        lines.append(row(lbl, "date", date))
    return lines


__all__ = [
    "render_email_delete",
    "render_email_forward",
    "render_email_reply",
    "render_email_send",
]
