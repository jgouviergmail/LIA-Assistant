"""Text measurement without a font (ADR-274).

python-pptx computes no autofit, PowerPoint applies none when a file is opened,
and python-pptx's own ``fit_text`` ignores the master's paragraph spacing — it
chose 21 pt where PowerPoint still measured 364 pt of overflow. So the renderer
measures the text ITSELF, before placing it.

CALIBRATED against PowerPoint 16 on 2026-09-08, 54 combinations of size,
bullet count and length on the 16:9 body frame (863.98 × 356.38 pt). Any
average glyph width in **[0.426, 0.493] em counts every line exactly**; 0.46 is
taken near the middle of that interval rather than at its floor, because the
calibration string ("mesure ") is narrower than real prose with capitals and
W's — aiming above the minimum absorbs that. Height is
``lines × size × 1.2 + paragraphs × size × 0.2``, times **1.05**, which turns
18 under-predictions into **none**. The measurements are the fixture of
``test_fit.py``.

Stated limit: these are Calibri metrics. Carlito (LibreOffice) is
metric-compatible; other viewers substitute a face of their own — the 14 pt
floor and the 5 % margin cover the common case, not every substitution.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from unicodedata import east_asian_width

#: Average glyph width as a fraction of the font size (measured, not guessed).
#: Zero-error interval [0.426, 0.493]; a value near the middle absorbs prose
#: wider than the calibration string.
AVG_CHAR_WIDTH_EM = 0.46
#: A full-width glyph is one em BY DEFINITION, not the width calibrated on
#: Latin prose. Counting an ideograph at 0.46 em measured a dense Chinese slide
#: at 238 pt where it takes 442 pt in a 356 pt frame — and the overflow oracle
#: agreed with the renderer, because both read this module.
FULL_WIDTH_EM = 1.0
#: East Asian Width classes that occupy a full em. "A" (ambiguous — the em
#: dash, degree signs) stays narrow: it is narrow in a Latin context, and
#: widening it would move every measurement the Latin calibration pinned.
_FULL_WIDTH_CLASSES = frozenset({"W", "F"})
#: The interval within which every calibration line count stays exact.
CALIBRATED_CHAR_WIDTH_RANGE: tuple[float, float] = (0.426, 0.493)
#: Line box as a fraction of the font size.
LINE_HEIGHT_FACTOR = 1.2
#: Space between paragraphs, as a fraction of the font size.
PARAGRAPH_SPACING_FACTOR = 0.2
#: The margin that turned 18 under-predictions into none.
SAFETY_FACTOR = 1.05
#: The placeholder's left/right inset in the default master (0.1 in).
INSET_PT = 7.2
#: Level-1 bullet indent of the default master.
BULLET_INDENT_PT = 27.0
#: Below this a slide stops being readable from the back of a room.
BODY_SIZE_FLOOR_PT = 14
BODY_SIZE_STEP_PT = 2
TITLE_SIZE_BASE_PT = 40
TITLE_SIZE_FLOOR_PT = 24
#: From this size down, a title may take two lines inside its frame.
TITLE_TWO_LINES_FROM_PT = 36
#: Row height a table needs at each of the two table font sizes.
TABLE_ROW_HEIGHT_PT: dict[int, float] = {12: 28.8, 10: 24.0}
#: Beyond this many columns a table needs the smaller font.
TABLE_WIDE_COLUMNS = 6

_SENTENCE_END = re.compile(r"(?<=[.!?。！？])\s+")


@dataclass(frozen=True, slots=True)
class TextFrame:
    """A placeholder's box, in points."""

    width_pt: float
    height_pt: float
    indent_pt: float = BULLET_INDENT_PT

    @property
    def usable_width(self) -> float:
        """Width left for glyphs once insets and the bullet indent are taken."""
        return max(1.0, self.width_pt - 2 * INSET_PT - self.indent_pt)


def text_width_em(text: str) -> float:
    """The width of a string in em, full-width glyphs counted as one.

    A Latin string measures exactly ``len(text) * AVG_CHAR_WIDTH_EM``, so every
    PowerPoint calibration measurement — all of them Latin — still holds.

    Args:
        text: Any string.

    Returns:
        The width in em (multiply by the font size for points).
    """
    if text.isascii():  # the common case, and never full-width
        return len(text) * AVG_CHAR_WIDTH_EM
    return sum(
        FULL_WIDTH_EM if east_asian_width(char) in _FULL_WIDTH_CLASSES else AVG_CHAR_WIDTH_EM
        for char in text
    )


def display_columns(text: str) -> float:
    """The width of a string counted in AVERAGE LATIN CHARACTERS.

    The unit Excel sizes a column in, and the one a proportional table weight
    needs: an ideograph is about two of them, a letter exactly one.

    Args:
        text: Any string.

    Returns:
        The width, never negative.
    """
    return text_width_em(text) / AVG_CHAR_WIDTH_EM


def line_count(text: str, size_pt: float, frame: TextFrame) -> int:
    """Lines one paragraph takes at ``size_pt`` — exact on the calibration set.

    Args:
        text: The paragraph.
        size_pt: Font size in points.
        frame: The box it is placed in.

    Returns:
        At least one line, even for an empty paragraph.
    """
    if not text:
        return 1
    return max(1, math.ceil(text_width_em(text) * size_pt / frame.usable_width))


def text_height(paragraphs: Sequence[str], size_pt: float, frame: TextFrame) -> float:
    """Height of the paragraphs at ``size_pt``, with the safety margin."""
    lines = sum(line_count(paragraph, size_pt, frame) for paragraph in paragraphs)
    spacing = len(paragraphs) * size_pt * PARAGRAPH_SPACING_FACTOR
    return (lines * size_pt * LINE_HEIGHT_FACTOR + spacing) * SAFETY_FACTOR


def fits(paragraphs: Sequence[str], size_pt: float, frame: TextFrame) -> bool:
    """Whether the paragraphs stay inside the frame at ``size_pt``."""
    return text_height(paragraphs, size_pt, frame) <= frame.height_pt


def base_body_size(count: int) -> int:
    """The starting body size by bullet count: airy for few, tighter for many."""
    if count <= 3:
        return 24
    return 20 if count <= 6 else 18


def choose_body_size(paragraphs: Sequence[str], frame: TextFrame) -> int | None:
    """The largest size from the base down to the floor that fits, or ``None``."""
    size = base_body_size(len(paragraphs))
    while size >= BODY_SIZE_FLOOR_PT:
        if fits(paragraphs, size, frame):
            return size
        size -= BODY_SIZE_STEP_PT
    return None


@dataclass(frozen=True, slots=True)
class SlidePlan:
    """The bullets of one slide and the size they are set at."""

    bullets: tuple[str, ...]
    size_pt: int


def _pieces_that_fit(text: str, frame: TextFrame) -> list[str]:
    """Cut one oversized paragraph at sentence ends, then at words, into fitting pieces.

    Nothing is ever dropped: what does not fit is carried to the next piece.
    """
    if fits([text], BODY_SIZE_FLOOR_PT, frame):
        return [text]
    units = [unit for unit in _SENTENCE_END.split(text) if unit]
    if len(units) == 1:
        units = text.split(" ")
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current} {unit}".strip()
        if current and not fits([candidate], BODY_SIZE_FLOOR_PT, frame):
            pieces.append(current)
            current = unit
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def plan_body(bullets: Sequence[str], frame: TextFrame) -> list[SlidePlan]:
    """Shrink first; when the floor is not enough, fill slides greedily in order.

    Args:
        bullets: The slide's bullets, in order.
        frame: The body placeholder.

    Returns:
        One plan per slide to produce; the bullets keep their order and none is
        lost — an oversized bullet is cut at sentence boundaries, never clipped.
    """
    if not bullets:
        return [SlidePlan((), base_body_size(0))]
    size = choose_body_size(bullets, frame)
    if size is not None:
        return [SlidePlan(tuple(bullets), size)]

    plans: list[SlidePlan] = []
    current: list[str] = []
    for piece in (piece for bullet in bullets for piece in _pieces_that_fit(bullet, frame)):
        if current and not fits([*current, piece], BODY_SIZE_FLOOR_PT, frame):
            plans.append(
                SlidePlan(tuple(current), choose_body_size(current, frame) or BODY_SIZE_FLOOR_PT)
            )
            current = []
        current.append(piece)
    if current:
        plans.append(
            SlidePlan(tuple(current), choose_body_size(current, frame) or BODY_SIZE_FLOOR_PT)
        )
    return plans


def fit_title(title: str, frame: TextFrame) -> tuple[int, int]:
    """(size, lines) for a title: shrink from the base, two lines from 36 pt down.

    Decides with the SAME ``fits`` the overflow oracle re-checks, so the two can
    never disagree about a title.
    """
    size = TITLE_SIZE_BASE_PT
    while size >= TITLE_SIZE_FLOOR_PT:
        lines = line_count(title, size, frame)
        allowed = 2 if size <= TITLE_TWO_LINES_FROM_PT else 1
        if lines <= allowed and fits([title], size, frame):
            return size, lines
        size -= BODY_SIZE_STEP_PT
    return TITLE_SIZE_FLOOR_PT, line_count(title, TITLE_SIZE_FLOOR_PT, frame)


def table_font_size(columns: int) -> int:
    """12 pt up to six columns, 10 pt beyond."""
    return 12 if columns <= TABLE_WIDE_COLUMNS else 10


def rows_per_slide(columns: int, frame: TextFrame) -> int:
    """Data rows one slide holds at the table's font size, header row excluded."""
    row_height = TABLE_ROW_HEIGHT_PT[table_font_size(columns)]
    return max(1, int(frame.height_pt / row_height) - 1)
