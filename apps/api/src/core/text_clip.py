"""Cutting display prose to a bound without cutting a word, or to one line.

One implementation for every surface that shortens a sentence a person reads:
an effect label under a chat bubble (ADR-263), the prose fields of a
relationship debrief (ADR-269), and the rows, titles and excerpts of a HITL
confirmation or of a draft's result (ADR-323). A cut in the middle of a word
reads as a defect — « posture cr » under a generated image (2026-09-23) —
while the same cut on a word boundary, ellipsis included, reads as
intentional. ``one_line`` draws a value inside one row the same way for
every HITL and draft preview: its line breaks folded, the typography's
spaces kept between words, and ``spell_unseen`` spells out in it what would
reorder the value or leave nothing to read. ``clip_data`` draws a value a
PROGRAM produced — a tool call's arguments, shown to a person asked to
allow it: every space folded and every character nobody sees spelled out,
a run of them one marker, so no run nobody sees spends the bound it cuts
the value to. What a person CAN see may still fill that bound —
seventy dots before an address hide it as well as a cut does — and the
ellipsis says so: a bound states its cut, it cannot tell padding from data.

What these functions return is read by a person, never parsed back by a
program. A card or a label cuts a COPY and the value stays whole where it
is used; the debrief stores what its schema clipped
(``relations/debrief/schemas.py``), its bound being part of what it keeps.
"""

from __future__ import annotations

import itertools
import re
import unicodedata
from collections.abc import Iterator

#: The mark a shortened text ends with — one character, counted in the bound.
ELLIPSIS = "…"

#: The word the bound falls inside, with the whitespace before it — any Unicode
#: whitespace, since French prose carries no-break spaces (« posture : »).
_PARTIAL_WORD = re.compile(r"\s+\S*$")

#: Separators a cut must not leave dangling before the ellipsis: « avant,… »
#: reads as a typo, « avant… » as a cut.
_DANGLING_SEPARATORS = re.compile(r"[\s,;:—–-]+$")


#: What ``one_line`` folds into one space: every ASCII character
#: ``str.isspace`` accepts (the information separators 0x1C-0x1F included)
#: and every line separator ``str.splitlines`` breaks on (a subject may carry
#: U+2028) — never a no-break, fixed-width or ideographic space: those belong
#: to the typography.
_ORDINARY_WHITESPACE = re.compile(r"[ \t\n\r\f\v\x1c-\x1f\x85\u2028\u2029]+")

#: The categories nobody sees whatever the code point: the format characters
#: (a zero-width space, a word joiner, a bidirectional override that reorders
#: what follows, the tag characters a model reads and a person does not) and
#: the control characters that are not whitespace (a backspace, an escape).
_INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc"})

#: The code points nobody sees in the other categories: the default-ignorable
#: ones of the Unicode Character Database that are not format characters (the
#: combining grapheme joiner, the Hangul fillers, the Khmer inherent vowels,
#: the Mongolian and the ordinary variation selectors, the unassigned
#: default-ignorable ranges) and the braille blank, a glyph that draws nothing.
_INVISIBLE_CODE_POINTS = frozenset(
    code
    for low, high in (
        (0x034F, 0x034F),
        (0x115F, 0x1160),
        (0x17B4, 0x17B5),
        (0x180B, 0x180F),
        (0x2065, 0x2065),
        (0x2800, 0x2800),
        (0x3164, 0x3164),
        (0xFE00, 0xFE0F),
        (0xFFA0, 0xFFA0),
        (0xFFF0, 0xFFF8),
        (0xE0000, 0xE0FFF),
    )
    for code in range(low, high + 1)
)

#: The combining marks that stack on a letter (nonspacing and enclosing).
_STACKING_CATEGORIES = frozenset({"Mn", "Me"})
#: What a stack of marks is made of for :func:`spell_unseen`: the marks and
#: whatever nobody sees between them.
_STACK_KINDS = frozenset({"mark", "hidden"})

#: How many combining marks a letter carries in real writing (two in
#: Vietnamese, three on a Hebrew letter with its points and cantillation): a
#: longer stack draws one smear and spends the bound on nothing to read.
_MAX_STACKED_MARKS = 4

#: How many distinct code points a marker names before it says « … ».
_MARKER_NAMES = 3

#: What a marker is drawn in: mathematical angle brackets, which no surface
#: reads as markup — ``<U+200B>`` was erased by the ticket's HTML stripper,
#: and a square bracket opens a Markdown link.
_MARKER_OPEN = "⟨"
_MARKER_CLOSE = "⟩"

#: The bidirectional controls that REORDER what follows them: the embeddings,
#: the overrides and the isolates. A right-to-left override inside a name
#: draws its end first; the marks (U+200E, U+200F, U+061C) only lean the
#: neutral characters around them, and right-to-left text carries them.
_REORDERING_RUN = re.compile("[\u202a-\u202e\u2066-\u2069]+")

#: How many characters of a text run the data drawing reads at a time. A
#: value is cut at a bound of tens of characters, and a megabyte e-mail body
#: passed as an argument used to be drawn whole before the cut (190 ms, on
#: the event loop, for one card).
_TEXT_CHUNK = 64


def clip_on_word(text: str, limit: int) -> str:
    """Cut prose to ``limit`` characters, ellipsis included, on a word boundary.

    The ellipsis is counted IN the bound: a clip that returned ``limit + 1``
    characters would need the stored contract to be one character looser than
    the published one, and two nearly-equal numbers is how they drift. A text
    whose kept part is a single token (a long URL, an unbroken name) is cut
    inside it, since that is the only cut there is.

    Args:
        text: The prose, already stripped by the caller when that matters.
        limit: Longest the result may be, ellipsis included; at least 1.

    Returns:
        ``text`` unchanged when it fits, else its head and an ellipsis.
    """
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    # The cut falls inside a word unless the first dropped character is
    # whitespace: drop the partial word, keep a complete one.
    on_word = head if text[limit - 1].isspace() else (_PARTIAL_WORD.sub("", head) or head)
    kept = _DANGLING_SEPARATORS.sub("", on_word)
    return f"{kept or head}{ELLIPSIS}"


def one_line(text: str) -> str:
    """``text`` on one line: each run of ordinary whitespace or line separators
    becomes one space.

    ``" ".join(text.split())`` folded a no-break space into an ordinary one
    too — the space a French colon takes — and the ideographic space with it.
    Between two words such a space is typography, and it stays; at an end it
    is nothing, and it goes — a label drawn in bold (``**label**``) is not
    bold when a space touches its markers.

    Args:
        text: A value drawn inside one line (an item preview).

    Returns:
        The text with its ordinary whitespace collapsed, every whitespace
        trimmed from its ends.
    """
    return _ORDINARY_WHITESPACE.sub(" ", text).strip()


def _drawn_as(char: str) -> str:
    """How :func:`clip_data` draws a character.

    Args:
        char: One character of the value.

    Returns:
        ``space``, ``hidden`` (nobody sees it), ``mark`` (a combining mark,
        which stacks on the letter before it) or ``text``.
    """
    if char.isspace():
        return "space"
    category = unicodedata.category(char)
    if category in _INVISIBLE_CATEGORIES or ord(char) in _INVISIBLE_CODE_POINTS:
        return "hidden"
    return "mark" if category in _STACKING_CATEGORIES else "text"


def _marker(run: str) -> str:
    """One marker for a run of characters: their code points, then their count.

    Written with no whitespace inside, so nothing that cuts, wraps or flattens
    on a space can split it.

    Args:
        run: Consecutive characters nobody sees — with the spaces between
            them, in a program's value — or one stack of marks.

    Returns:
        ``⟨U+200B⟩`` for one character, ``⟨U+200B×70⟩`` for a run of one code
        point, the first three distinct code points of a mixed run in the order
        they appear and « … » for the rest (``⟨U+200B,U+0020×69⟩``).
    """
    distinct = list(dict.fromkeys(run))
    names = ",".join(f"U+{ord(char):04X}" for char in distinct[:_MARKER_NAMES])
    others = ",…" if len(distinct) > _MARKER_NAMES else ""
    count = f"×{len(run)}" if len(run) > 1 else ""
    return f"{_MARKER_OPEN}{names}{others}{count}{_MARKER_CLOSE}"


def _spelled(kind: str, run: str) -> bool:
    """Whether a run is drawn as a marker: what nobody sees, or a smear.

    Args:
        kind: The run's kind (:func:`_drawn_as`).
        run: The run.

    Returns:
        True for characters nobody sees and for a stack of marks longer than
        any script writes.
    """
    return kind == "hidden" or (kind == "mark" and len(run) > _MAX_STACKED_MARKS)


def spell_unseen(text: str) -> str:
    """A label as it is written, what would mislead its reader spelled out.

    For the name a person reads to recognise a thing — a card's title, a
    batch row, a field's value: its typography stays, and so does a joiner
    inside an emoji or a variation selector, which draw what they should. Two
    things are spelled as markers: a bidirectional control that reorders what
    follows (a tool name ending in an override read backwards), and a stack of
    marks longer than any script writes — counted across what nobody sees
    between them, as one smear. A value in which nothing at all can be seen is
    spelled whole: a title of zero-width spaces headed a card with nothing.

    Args:
        text: The label, on one line when it is one.

    Returns:
        The label, spelled where it would mislead.
    """
    runs = [(kind, "".join(characters)) for kind, characters in itertools.groupby(text, _drawn_as)]
    if runs and not any(kind == "text" for kind, _ in runs):
        return "".join(_marker(run) if _spelled(kind, run) else run for kind, run in runs)
    return "".join(
        _spell_stack(list(group), stacked)
        for stacked, group in itertools.groupby(runs, key=lambda run: run[0] in _STACK_KINDS)
    )


def _spell_stack(stack: list[tuple[str, str]], stacked: bool) -> str:
    """Spell one uninterrupted group of marks or hidden controls."""
    marks = sum(len(run) for kind, run in stack if kind == "mark")
    if stacked and marks > _MAX_STACKED_MARKS:
        # One smear, whatever joins it: a joiner or a variation selector
        # between the marks kept them one cluster (review 14).
        return _marker("".join(run for _, run in stack))
    return "".join(
        _REORDERING_RUN.sub(lambda match: _marker(match.group(0)), run) if kind == "hidden" else run
        for kind, run in stack
    )


def clip_spelled(text: str, limit: int) -> str:
    """A label spelled (:func:`spell_unseen`), then cut on a word to ``limit``.

    Spelled AFTER the cut, a value passed its bound — a marker is longer than
    what it names (sixty characters became two hundred and seventy); cut on a
    word after the spelling, the cut could fall inside a marker (review 14). A
    marker is kept whole or left out with what follows it, as in
    :func:`clip_data`; one the bound cannot hold at all is cut, the only cut
    there is.

    Args:
        text: The label or excerpt, on one line when it is one.
        limit: Longest the result may be, ellipsis included; at least 1.

    Returns:
        The spelled text, whole when it fits, else its head and an ellipsis.
    """
    spelled = spell_unseen(text)
    clipped = clip_on_word(spelled, limit)
    if clipped == spelled:
        return spelled
    kept = clipped[: -len(ELLIPSIS)]
    opened = kept.rfind(_MARKER_OPEN)
    if opened > kept.rfind(_MARKER_CLOSE):
        whole = _DANGLING_SEPARATORS.sub("", kept[:opened])
        if whole:
            return f"{whole}{ELLIPSIS}"
    return clipped


def _blank_pieces(
    blank: list[tuple[str, str]], *, started: bool, ended: bool
) -> Iterator[tuple[bool, str]]:
    """Draw one run of whitespace, invisible characters and baseless marks.

    Args:
        blank: The run's groups, as ``(kind, characters)``.
        started: Whether something was drawn before the run.
        ended: Whether the value ends with the run.

    Yields:
        One space for whitespace alone; otherwise ONE marker for everything
        from the first character nobody sees to the last (the spaces between
        them included), with one space on either side where the run had some
        — never at the value's ends.
    """
    seen = [index for index, (kind, _) in enumerate(blank) if kind != "space"]
    if not seen:
        if started and not ended:
            yield False, " "
        return
    first, last = seen[0], seen[-1]
    if first > 0 and started:
        yield False, " "
    yield False, _marker("".join(run for _, run in blank[first : last + 1]))
    if last < len(blank) - 1 and not ended:
        yield False, " "


def _data_pieces(text: str) -> Iterator[tuple[bool, str]]:
    """The drawing of a program's value, piece by piece, read as it is drawn.

    A piece is a run of text, one space or one marker. Whitespace, characters
    nobody sees and marks that stack on no letter make ONE run: seventy
    zero-width spaces between seventy spaces are one marker, where one marker
    each filled a card's bound. Text is read a chunk at a time, so a cut stops
    the reading.

    Args:
        text: The value's text.

    Yields:
        ``(cuttable, piece)`` in order — only a run of text may be cut.
    """
    blank: list[tuple[str, str]] = []
    started = False
    for kind, characters in itertools.groupby(text, key=_drawn_as):
        if kind != "text" and (kind != "mark" or blank or not started):
            blank.append((kind, "".join(characters)))
            continue
        if blank:
            yield from _blank_pieces(blank, started=started, ended=False)
            blank = []
        if kind == "mark":
            # A stack on the letter before it: writing, or a smear.
            run = "".join(characters)
            yield (False, _marker(run)) if _spelled(kind, run) else (True, run)
        else:
            while chunk := "".join(itertools.islice(characters, _TEXT_CHUNK)):
                yield True, chunk
        started = True
    if blank:
        yield from _blank_pieces(blank, started=started, ended=True)


def clip_data(text: str, limit: int) -> str:
    """A value a program produced, on one line, all of it shown, cut to ``limit``.

    Every run of whitespace — typographic spaces included, since a program's
    value carries no typography — becomes one space. Every run of characters
    nobody sees, with the spaces around and between them, becomes ONE marker
    naming its code points and its length (``⟨U+200B×70⟩``), so seventy
    zero-width spaces cost a card eleven characters of its bound rather than
    all of them; a stack of combining marks longer than any script writes, or
    marks stacked on no letter, are spelled out the same way. The price falls
    on the legitimate uses of the same characters, deliberately: a joiner
    inside an emoji or a Persian word, a soft hyphen, a variation selector are
    spelled out too — this is data a person is asked to allow, not prose to
    typeset.

    Data is cut INSIDE a token, never on a word: cut on a word, « GET
    https://evil.example/… » kept « GET » and dropped the host, and a value
    padded with two zero-width spaces showed nothing but their marker. A
    marker is never cut — kept whole, or left out with what follows it. The
    ellipsis is counted in the bound. A run of text is read only as far as
    the bound needs; a run of what nobody sees is read whole — its length is
    part of its marker, and what follows it must still be shown.

    Args:
        text: The value's text (a string, or the JSON spelling of a value).
        limit: Longest the result may be, ellipsis included; at least 1.

    Returns:
        The drawing, whole when it fits, else its head and an ellipsis.
    """
    pieces: list[tuple[bool, str]] = []
    length = 0
    for piece in _data_pieces(text):
        pieces.append(piece)
        length += len(piece[1])
        if length > limit:
            break
    else:
        return "".join(drawn for _, drawn in pieces)
    kept: list[str] = []
    room = limit - 1
    for cuttable, drawn in pieces:
        if len(drawn) > room:
            if cuttable:
                kept.append(drawn[:room])
            break
        kept.append(drawn)
        room -= len(drawn)
    return "".join(kept).rstrip(" ") + ELLIPSIS
