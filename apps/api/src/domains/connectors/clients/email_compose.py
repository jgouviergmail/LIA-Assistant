"""What a reply or a forward says, whatever the mailbox (ADR-344).

Graph composes its replies server-side; Gmail and IMAP build theirs by hand,
and a reply saved as a mailbox draft must be the message sending it would have
sent. The recipients, the subject and the quoted history are therefore decided
here, once, and every hand-built composition reads them.

Recipients are compared on their PARSED address, never on header text
(``infrastructure/email/recipients``): Apple's reply used to split a header on
commas (a display name may hold one) and to compare the raw value with the
account's address, so a person named in the original by a display name was
copied on their own reply; Gmail's dropped every other recipient of the
original from a reply to all.
"""

from __future__ import annotations

from email.utils import formataddr

from src.infrastructure.email.recipients import read_recipients

#: The line that opens a forwarded message — Gmail's own wording.
_FORWARD_BANNER = "---------- Forwarded message ---------"


def _addresses(*headers: str) -> list[tuple[str, str]]:
    """Every readable ``(name, address)`` the received headers name, in order."""
    return [pair for header in headers for pair in read_recipients(header)]


def _keep_new(pairs: list[tuple[str, str]], seen: set[str]) -> list[tuple[str, str]]:
    """The pairs whose address is not in ``seen``, each added to it once kept."""
    kept: list[tuple[str, str]] = []
    for name, addr in pairs:
        key = addr.casefold()
        if key not in seen:
            seen.add(key)
            kept.append((name, addr))
    return kept


def _header(pairs: list[tuple[str, str]]) -> str:
    return ", ".join(formataddr(pair) for pair in pairs)


def reply_recipients(
    original_from: str,
    original_to: str,
    original_cc: str,
    *,
    own_address: str | None,
    reply_all: bool,
    override_to: str | None = None,
    reply_to: str | None = None,
) -> tuple[str, str]:
    """The ``(To, Cc)`` of a reply, addressed the way mail clients address it.

    A reply goes to ``Reply-To`` when present, otherwise the sender. A reply
    to all answers the other ``To`` recipients and copies the original ``Cc``,
    as Gmail, Outlook and Graph's
    ``replyAll`` do. The person's own address is never a recipient, and a
    reply to the person's OWN message answers the people it was sent to. A
    chosen recipient replaces the answered ones and keeps the copies — Graph's
    ``replyAll`` with an overriding ``toRecipients``.

    Args:
        original_from: The original's ``From`` header.
        original_to: The original's ``To`` header.
        original_cc: The original's ``Cc`` header.
        own_address: The mailbox's address, when known.
        reply_all: Answer every recipient of the original.
        override_to: A recipient the person chose instead.
        reply_to: The original's ``Reply-To`` header, when present.

    Returns:
        The ``To`` header (the original reply address verbatim leads it when the
        sender is answered) and the ``Cc`` header (empty when nobody is copied).
    """
    own = (own_address or "").casefold()
    seen = {own} if own else set()
    sender = _addresses(original_from)
    if override_to:
        to_header = override_to
        _keep_new(_addresses(override_to), seen)
    elif own and sender and sender[0][1].casefold() == own:
        to_header = _header(_keep_new(_addresses(original_to), seen)) or original_from
    else:
        answer_header = reply_to or original_from
        _keep_new(_addresses(answer_header), seen)
        others = _keep_new(_addresses(original_to), seen) if reply_all else []
        to_header = ", ".join([answer_header, *(formataddr(pair) for pair in others)])
    cc_header = _header(_keep_new(_addresses(original_cc), seen)) if reply_all else ""
    return to_header, cc_header


def reply_subject(subject: str) -> str:
    """The subject of a reply: ``Re:`` once, whatever its case."""
    return subject if subject.lower().startswith("re:") else f"Re: {subject}"


def forward_subject(subject: str) -> str:
    """The subject of a forward: ``Fwd:`` once, whatever its case."""
    return subject if subject.lower().startswith("fwd:") else f"Fwd: {subject}"


def quoted_reply(body: str, original_body: str, *, date: str, sender: str, is_html: bool) -> str:
    """The reply's words above the original, quoted the way mail clients quote.

    An HTML reply, or an original with no text, quotes nothing.
    """
    if not original_body or is_html:
        return body
    quoted = "\n".join(f"> {line}" for line in original_body.strip().splitlines())
    return f"{body}\n\nOn {date}, {sender} wrote:\n{quoted}"


def forwarded_body(
    body: str | None, original_body: str, *, sender: str, date: str, subject: str, to: str
) -> str:
    """The forward's words above the original message and its headers."""
    return (
        f"{body or ''}\n\n{_FORWARD_BANNER}\n"
        f"From: {sender}\nDate: {date}\nSubject: {subject}\nTo: {to}\n\n{original_body}"
    )


__all__ = [
    "forward_subject",
    "forwarded_body",
    "quoted_reply",
    "reply_recipients",
    "reply_subject",
]
