"""Who an outgoing e-mail is addressed to, read once for every road (ADR-344).

A recipient field arrives from a model or a person: ``,`` or ``;`` between
addresses, a separator left at the end, a display name holding a comma.
Python's parser is strict since 3.13 — one stray separator turns the whole
field into ``('', '')``, and an address it cannot read answers the same pair as
an empty segment — so the field is cut HERE first, outside quotes and angle
brackets, and each segment is read alone.

Two readers, for two sources:

* :func:`parse_recipients` reads what LIA is about to WRITE: an unreadable or
  invalid address refuses the whole field — a recipient dropped in silence is a
  message that never reaches someone the person named;
* :func:`read_recipients` reads a header a provider HANDED us: what it cannot
  read is skipped, because refusing would make a reply to a mangled header
  impossible.

A refusal never quotes the address: an exception text reaches logs above DEBUG
(ADR-317).
"""

from __future__ import annotations

from email.header import Header
from email.utils import formataddr, getaddresses

from src.core.validators import validate_email

__all__ = [
    "encode_recipients",
    "parse_recipients",
    "read_recipients",
    "recipient_segments",
    "same_recipients",
]


def _span_ends(field: str) -> dict[int, int]:
    """Locate complete quoted/bracketed spans in linear time, including malformed input.

    Walk backwards so an unclosed span never scans the same suffix again.
    Within quotes, a backslash consumes its following non-newline character.
    An unclosed quote or bracket has no span and is treated as plain text.
    """
    ends: dict[int, int] = {}
    next_bracket: int | None = None
    next_quote: int | None = None
    quote_after_next: int | None = None
    for index in range(len(field) - 1, -1, -1):
        char = field[index]
        if char == ">":
            next_bracket = index
        elif char == "<" and next_bracket is not None:
            ends[index] = next_bracket + 1
        quote_here = next_quote
        if char == '"':
            if next_quote is not None:
                ends[index] = next_quote + 1
            quote_here = index
        elif char == "\\":
            quote_here = (
                quote_after_next if index + 1 < len(field) and field[index + 1] != "\n" else None
            )
        quote_after_next, next_quote = next_quote, quote_here
    return ends


def _segments(field: str) -> list[str]:
    """The field cut on ``,`` and ``;`` outside quotes and angle brackets, blanks dropped."""
    ends = _span_ends(field)
    segments: list[str] = []
    start = index = 0
    while index < len(field):
        if index in ends:
            index = ends[index]
            continue
        if field[index] in ",;":
            if segment := field[start:index].strip():
                segments.append(segment)
            start = index + 1
        index += 1
    if segment := field[start:].strip():
        segments.append(segment)
    return segments


def _read(segment: str) -> tuple[str, str] | None:
    """The one valid ``(name, address)`` a segment names, or None."""
    pairs = getaddresses([segment])
    if len(pairs) != 1:
        return None
    name, address = pairs[0]
    return (name, address) if validate_email(address) else None


def recipient_segments(field: str) -> list[tuple[str, bool]]:
    """Each recipient a field names, as written, and whether it is an address.

    For a reader that resolves what is NOT an address yet (a contact's name):
    the field is read segment by segment, never judged by its first one.

    Args:
        field: Recipients separated by ``,`` or ``;``.

    Returns:
        ``(segment, is_address)`` pairs, in order; empty for a blank field.
    """
    return [(segment, _read(segment) is not None) for segment in _segments(field)]


def parse_recipients(field: str) -> list[tuple[str, str]]:
    """Every recipient a field names, or a refusal.

    Args:
        field: Addresses separated by ``,`` or ``;``, each bare or
            ``Name <address>``.

    Returns:
        The ``(name, address)`` pairs, in order; empty for a blank field.

    Raises:
        ValueError: A segment is not one readable, complete address.
    """
    recipients: list[tuple[str, str]] = []
    for segment in _segments(field):
        pair = _read(segment)
        if pair is None:
            raise ValueError(
                "Invalid email address format: every recipient must be a complete "
                "address (e.g. user@example.com)."
            )
        recipients.append(pair)
    return recipients


def read_recipients(field: str) -> list[tuple[str, str]]:
    """Every readable recipient of a header a provider handed us.

    Args:
        field: A ``To``, ``Cc`` or ``From`` header as received.

    Returns:
        The readable ``(name, address)`` pairs, in order; the rest is skipped.
    """
    return [pair for segment in _segments(field) if (pair := _read(segment)) is not None]


def same_recipients(left: str | None, right: str | None) -> bool:
    """Whether two recipient fields name the same people, display names aside.

    « Paul <paul@x.com> » and « paul@x.com » are one recipient. A field holding
    something nobody can read is the same only as itself: calling it unchanged
    would hide what the mailbox will refuse.

    Args:
        left: A recipient field, or None.
        right: Another one, or None.

    Returns:
        True when both name the same addresses, in any order.
    """
    if (left or "").strip() == (right or "").strip():
        return True

    def readable(field: str | None) -> set[str] | None:
        segments = recipient_segments(field or "")
        if not all(is_address for _, is_address in segments):
            return None
        return {address.casefold() for _, address in read_recipients(field or "")}

    named = readable(left)
    return named is not None and named == readable(right)


def encode_recipients(field: str) -> str:
    """A recipient field ready for a header, its display names RFC 2047-encoded.

    Only a NAME outside ASCII is encoded, so the addresses stay outside every
    encoded word: assigned raw to a ``MIMEMultipart`` header, a value holding an
    accent was encoded WHOLE, addresses included — the recipient saw a name and
    no address (found on Apple's send while building the drafts, ADR-344).

    Args:
        field: Addresses separated by ``,`` or ``;``, bare or ``Name <address>``.

    Returns:
        The addresses joined by ``", "``; empty for a blank field.

    Raises:
        ValueError: A segment is not one readable, complete address.
    """
    encoded: list[str] = []
    for name, address in parse_recipients(field):
        if name and not name.isascii():
            name = Header(name, "utf-8").encode()
        encoded.append(formataddr((name, address)) if name else address)
    return ", ".join(encoded)
