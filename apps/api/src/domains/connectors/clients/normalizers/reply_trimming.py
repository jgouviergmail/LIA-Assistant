"""The quoted history and the signature leave a reply before a model reads it (ADR-287).

A thread of eight replies reached the model eight times over — every reply
quotes the whole history, and nothing removed it — and a signature block
travelled with every message. This module keeps the person's OWN words: it
cuts at the first marker that opens the quoted history (a "wrote:" line in
six languages, an "Original Message" banner, an Outlook header block, a
trailing run of ``>`` lines) or the signature (``-- `` or a "sent from my"
line), and returns the body unchanged when cutting would leave too little
to stand alone or when the quote is interleaved with answers.

Measured on a corpus of 48 bodies (eight families × six languages) by
``tests/unit/domains/connectors/clients/normalizers/test_reply_trimming.py``;
``task emails:corpus:measure`` replays it and scores a third-party trimmer
beside this one when one is installed, so the choice stays measured.
"""

from __future__ import annotations

import re

#: Below this many characters the person's own words cannot stand alone
#: (a bare « Merci ! »): the quote is what the reader will want, keep it all.
MIN_KEPT_CHARS = 20

# One line that opens the quoted history, in the six languages LIA speaks.
# Each is anchored to a whole line; the mail clients wrap the long ones
# (Gmail at ~76 columns), which is why the search also tries two joined lines.
_QUOTE_HEADER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^Le .{4,160} a écrit\s*:\s*$"),  # fr
    re.compile(r"^On .{4,160} wrote:\s*$"),  # en
    re.compile(r"^Am .{4,160} schrieb .{1,160}:\s*$"),  # de
    re.compile(r"^El .{4,160} escribió:\s*$"),  # es
    re.compile(r"^Il giorno .{4,160} ha scritto:\s*$"),  # it
    re.compile(r"^在.{2,160}写道[：:]\s*$"),  # zh
    re.compile(
        r"^-{2,}\s*(Original Message|Message d'origine|Ursprüngliche Nachricht|"
        r"Mensaje original|Messaggio originale|原始邮件)\s*-{2,}\s*$",
        re.IGNORECASE,
    ),
)

# An Outlook-style header block: a "From:" line followed, within a few
# lines, by a "Subject:" line — the two together are the mark, never one alone.
_HEADER_FROM = re.compile(r"^(From|De|Von|Da|发件人)\s*[:：]\s*\S")
_HEADER_SUBJECT = re.compile(r"^(Subject|Objet|Betreff|Asunto|Oggetto|主题)\s*[:：]")
_HEADER_BLOCK_SPAN = 5

_SIGNATURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^-- ?$"),  # the RFC 3676 signature separator
    re.compile(
        r"^(Envoyé de mon|Sent from my|Von meinem .{1,40} gesendet|Enviado desde mi|"
        r"Inviato da|发自我的)\b"
    ),
)

_QUOTED_LINE = re.compile(r"^>")

# A forward is never trimmed: the text under its header block IS the message.
# Recognised by the subject prefix the six languages' clients write, or by the
# banner Gmail / Apple Mail / Outlook put above the forwarded headers.
_FORWARD_SUBJECT = re.compile(r"^\s*(?:fwd?|tr|wg|rv|i|转发)\s*[:：]", re.IGNORECASE)
_FORWARD_BANNER = re.compile(
    r"(?:Forwarded message|Begin forwarded message|Message transf[ée]r[ée]|"
    r"D[ée]but du message r[ée]exp[ée]di[ée]|Weitergeleitete Nachricht|"
    r"Anfang der weitergeleiteten Nachricht|Mensaje reenviado|Inicio del mensaje reenviado|"
    r"Messaggio inoltrato|Inizio messaggio inoltrato|转发的?邮件)",
    re.IGNORECASE,
)


def is_forward(text: str, subject: str | None) -> bool:
    """Whether the message forwards another one (by subject prefix or banner)."""
    if subject and _FORWARD_SUBJECT.match(subject):
        return True
    return bool(_FORWARD_BANNER.search(text))


def _first_quote_header(lines: list[str]) -> int | None:
    """Index of the first line (or pair of lines) that opens the quoted history."""
    for index, line in enumerate(lines):
        candidates = [line.strip()]
        if index + 1 < len(lines):
            candidates.append(f"{line.strip()} {lines[index + 1].strip()}")
        for candidate in candidates:
            if any(pattern.match(candidate) for pattern in _QUOTE_HEADER_PATTERNS):
                return index
    return None


def _first_header_block(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if not _HEADER_FROM.match(line.strip()):
            continue
        window = lines[index + 1 : index + 1 + _HEADER_BLOCK_SPAN]
        if any(_HEADER_SUBJECT.match(other.strip()) for other in window):
            return index
    return None


def _trailing_quote_start(lines: list[str]) -> int | None:
    """Index of the first ``>`` line when everything after it is quoted or blank.

    Answers interleaved with the quote (a ``>`` line followed by the person's
    own line) are left whole: cutting there would drop the answers.
    """
    for index, line in enumerate(lines):
        if not _QUOTED_LINE.match(line):
            continue
        rest = lines[index:]
        if all(_QUOTED_LINE.match(other) or not other.strip() for other in rest):
            return index
        return None
    return None


def _first_signature(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if any(pattern.match(line.rstrip("\r")) for pattern in _SIGNATURE_PATTERNS):
            return index
    return None


def trim_quoted_reply(text: str, *, subject: str | None = None) -> str:
    """Keep the person's own words; drop the quoted history and the signature.

    Args:
        text: A clean text body (never markup).
        subject: The message subject when known — a forward prefix keeps the
            body whole.

    Returns:
        The body cut at the first marker, trailing blank lines removed — or the
        body unchanged when no marker is found, when the message is a forward,
        when the quote is interleaved with answers, or when what would remain
        is shorter than :data:`MIN_KEPT_CHARS`.
    """
    if not text or not text.strip():
        return text
    if is_forward(text, subject):
        return text
    lines = text.split("\n")
    cuts = [
        cut
        for cut in (
            _first_quote_header(lines),
            _first_header_block(lines),
            _trailing_quote_start(lines),
            _first_signature(lines),
        )
        if cut is not None
    ]
    if not cuts:
        return text
    kept = "\n".join(lines[: min(cuts)]).rstrip()
    if len(kept.strip()) < MIN_KEPT_CHARS:
        return text
    return kept


def clean_reply_body(text: str, *, subject: str | None = None) -> str:
    """The door the normalisers call: :func:`trim_quoted_reply` under the
    ``emails_trim_quoted_replies`` switch, the body untouched when it is off."""
    from src.core.config import settings

    if not settings.emails_trim_quoted_replies:
        return text
    return trim_quoted_reply(text, subject=subject)


__all__ = ["MIN_KEPT_CHARS", "clean_reply_body", "is_forward", "trim_quoted_reply"]
