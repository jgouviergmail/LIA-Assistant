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

A provider's PREVIEW of a message is its first characters on one line, so a
short reply runs straight into what it quotes (measured on Graph, 2026-11-11:
seventeen characters of a reply, then forty underscores and the quoted header
block). :func:`preview_own_words` searches the same markers INSIDE that line
(ADR-379): « what I answered » is the writer's words alone.
"""

from __future__ import annotations

import re

from src.core.text_clip import one_line

#: Below this many characters the person's own words cannot stand alone
#: (a bare « Merci ! »): the quote is what the reader will want, keep it all.
MIN_KEPT_CHARS = 20

# The banner some clients write above the message they quote, in the six languages.
_ORIGINAL_MESSAGE_WORDS = (
    r"Original Message|Message d'origine|Ursprüngliche Nachricht|"
    r"Mensaje original|Messaggio originale|原始邮件"
)

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
    re.compile(rf"^-{{2,}}\s*({_ORIGINAL_MESSAGE_WORDS})\s*-{{2,}}\s*$", re.IGNORECASE),
)

# An Outlook-style header block: a "From:" line followed, within a few
# lines, by a "Subject:" line — the two together are the mark, never one alone.
_FROM_WORDS = "From|De|Von|Da|发件人"
_SUBJECT_WORDS = "Subject|Objet|Betreff|Asunto|Oggetto|主题"
_HEADER_FROM = re.compile(rf"^({_FROM_WORDS})\s*[:：]\s*\S")
_HEADER_SUBJECT = re.compile(rf"^({_SUBJECT_WORDS})\s*[:：]")
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
        stripped = line.strip()
        # No header starts on an empty line. Retain the original index so a
        # wrapped header and the kept body preserve every preceding line.
        if not stripped:
            continue
        candidates = [stripped]
        if index + 1 < len(lines):
            candidates.append(f"{stripped} {lines[index + 1].strip()}")
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
        if not line.strip():
            continue
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


# A line that IS a forward banner (dashes allowed around it), never a sentence
# that merely names a forwarded message.
_FORWARD_BANNER_LINE = re.compile(rf"^[-_\s]*(?:{_FORWARD_BANNER.pattern})", re.IGNORECASE)


def _first_forward_banner(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _FORWARD_BANNER_LINE.match(line.strip()):
            return index
    return None


def split_quoted_history(text: str) -> tuple[str, str]:
    """Tell a draft's own words from the history it quotes or forwards.

    The markers are the trimmer's, measured on the ADR-287 corpus, plus the
    forward banner; two differences belong to a DRAFT being edited: the
    signature is the person's own text and stays above the cut, and no minimum
    length applies (an empty reply still carries its history).

    Args:
        text: A clean text body (never markup).

    Returns:
        ``(own_words, history)`` with ``own_words + history == text`` exactly;
        ``history`` is empty when the body quotes nothing.
    """
    if not text:
        return text, ""
    lines = text.split("\n")
    cuts = [
        cut
        for cut in (
            _first_quote_header(lines),
            _first_header_block(lines),
            _trailing_quote_start(lines),
            _first_forward_banner(lines),
        )
        if cut is not None
    ]
    if not cuts:
        return text, ""
    start = min(cuts)
    own = "\n".join(lines[:start]) + "\n" if start else ""
    return own, "\n".join(lines[start:])


# --- The same markers, searched INSIDE one line: a provider's preview ---------------

#: How much of a preview is read. Providers hand over two hundred characters or so,
#: and every span below is bounded: the search is linear in what it reads.
_PREVIEW_READ_MAX_CHARS = 600

# The "wrote" line of each language as it reads inside a line: from its first word to
# its last, never across another first word (a French reply may say « On se voit
# jeudi. » right before an English header). Held to the line patterns above by the
# corpus both readers are tested on.
_INLINE_WROTE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?<!\w)Le (?:(?!Le ).){4,160}? a écrit\s*:"),  # fr
    re.compile(r"(?<!\w)On (?:(?!On ).){4,160}? wrote:"),  # en
    re.compile(r"(?<!\w)Am (?:(?!Am ).){4,160}? schrieb "),  # de
    re.compile(r"(?<!\w)El (?:(?!El ).){4,160}? escribió:"),  # es
    re.compile(r"(?<!\w)Il giorno (?:(?!Il giorno ).){4,160}? ha scritto:"),  # it
    re.compile(r"(?<!\w)在(?:(?!在).){2,160}?写道[：:]"),  # zh
)

# A banner above the quoted or forwarded message, its dashes included: the words
# alone are prose (« see the forwarded message »). A run of dashes is read ONCE, from
# its first dash and never given back: six hundred dashes cost 22 ms otherwise.
_INLINE_BANNER = re.compile(
    rf"(?<!-)-{{2,}}+\s*(?:{_ORIGINAL_MESSAGE_WORDS}|{_FORWARD_BANNER.pattern})", re.IGNORECASE
)

# A header block on one line: the sender line, then the subject line within reach.
_INLINE_HEADER_BLOCK = re.compile(
    rf"(?<!\w)(?:{_FROM_WORDS})\s*[:：]\s*\S.{{0,400}}?(?<!\w)(?:{_SUBJECT_WORDS})\s*[:：]"
)

# The rule Outlook draws between a reply and the block it quotes (forty underscores,
# measured on Graph); a blank to fill in is shorter.
_INLINE_RULE = re.compile(r"_{10,}")

# A quoted line's mark as it reads inside one line.
_INLINE_QUOTE_MARK = re.compile(r"(?:^|(?<=\s))>(?=\s|$)")


def _first_wrote_line(text: str) -> int | None:
    """Where the first "wrote" line starts; one that carries no date is prose."""
    starts = [
        match.start()
        for pattern in _INLINE_WROTE_PATTERNS
        for match in pattern.finditer(text)
        if any(char.isdigit() for char in match.group())
    ]
    return min(starts, default=None)


def _first_quoted_line(text: str) -> int | None:
    """Where the quoted lines start: two marks at least, one alone is a comparison."""
    marks = [match.start() for match in _INLINE_QUOTE_MARK.finditer(text)]
    return marks[0] if len(marks) > 1 else None


def preview_own_words(preview: str) -> str:
    """What a message's PREVIEW says before the history it quotes or forwards.

    The markers are the trimmer's, searched inside the line. Two differences belong to
    an excerpt of « what was answered »: the signature is the writer's own text and
    stays, and no minimum length applies (« Merci ! » is all that was said).

    Args:
        preview: A provider's preview of a message: the first characters of its body.

    Returns:
        The writer's words on one line, EMPTY when the preview opens on the history
        (an answer written under its quote): words that may be someone else's are
        never handed over as the writer's. A marker the preview's own bound cut in
        two is not recognised: what follows it stays.
    """
    # Cut before it is folded: folding only shortens, and a megabyte is never read.
    text = one_line(preview[:_PREVIEW_READ_MAX_CHARS])
    found = (
        match.start()
        for pattern in (_INLINE_BANNER, _INLINE_HEADER_BLOCK, _INLINE_RULE)
        if (match := pattern.search(text)) is not None
    )
    cuts = [
        cut
        for cut in (_first_wrote_line(text), _first_quoted_line(text), *found)
        if cut is not None
    ]
    return text[: min(cuts)].rstrip() if cuts else text


def clean_reply_body(text: str, *, subject: str | None = None) -> str:
    """The door the normalisers call: :func:`trim_quoted_reply` under the
    ``emails_trim_quoted_replies`` switch, the body untouched when it is off."""
    from src.core.config import settings

    if not settings.emails_trim_quoted_replies:
        return text
    return trim_quoted_reply(text, subject=subject)


__all__ = [
    "MIN_KEPT_CHARS",
    "clean_reply_body",
    "is_forward",
    "preview_own_words",
    "split_quoted_history",
    "trim_quoted_reply",
]
