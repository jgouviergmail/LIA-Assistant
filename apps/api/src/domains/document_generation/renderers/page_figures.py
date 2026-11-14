"""A report's band of key figures, planned once for Word and the PDF (ADR-274).

The writer says which few numbers carry the message; the band sets them side by
side as shaded tiles, each value over what it measures. Planned here, drawn by
each renderer in its own terms — a Word table of shaded cells, an HTML table the
PDF lays out — so a band reads the same in both:

- as few rows as fit, as even as possible (``fit.balanced_rows``): six figures
  read 3 + 3, never 4 + 2;
- one value size for the whole band: each row's base size shrunk until its
  WIDEST value fits its tile on one line, and the band takes the smallest —
  five figures read 3 + 2, and the two wider tiles below must not shout over
  the three above (measured on a page 2026-11-13). Figures side by side read as
  a set only if they look like one. Below the floor a value wraps inside its
  tile rather than shrink further — it never runs out of it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from src.domains.document_generation import typography
from src.domains.document_generation.fit import balanced_rows, text_width_em
from src.domains.document_generation.schemas import KeyFigure

#: Sizes are rounded down to this step, so a row never claims more than it measured.
_SIZE_STEP_PT = 0.5


@dataclass(frozen=True, slots=True)
class BandRow:
    """One row of the band.

    Attributes:
        figures: The row's figures, in order.
        value_pt: The size every value of the band is set in.
        tile_width_pt: The width of each tile, padding included.
    """

    figures: tuple[KeyFigure, ...]
    value_pt: float
    tile_width_pt: float


def _value_size(figures: Sequence[KeyFigure], room_pt: float, narrow_em: float) -> float:
    """The row's base size, shrunk until its widest value fits ``room_pt`` on one line."""
    base = float(typography.PAGE_FIGURE_VALUE_PT[len(figures)])
    widest = max(text_width_em(figure.value, narrow_em=narrow_em) for figure in figures)
    if widest <= 0:
        return base
    fitting = room_pt / (widest * typography.BOLD_WIDTH_FACTOR)
    stepped = math.floor(fitting / _SIZE_STEP_PT) * _SIZE_STEP_PT
    return max(float(typography.PAGE_FIGURE_VALUE_FLOOR_PT), min(base, stepped))


def plan_band(figures: Sequence[KeyFigure], width_pt: float, *, narrow_em: float) -> list[BandRow]:
    """The rows of a band of key figures across ``width_pt``.

    Args:
        figures: The block's figures, canonical (each carries its value).
        width_pt: The width the band spans: the text width of its page.
        narrow_em: The average width of a narrow glyph in the face the renderer
            sets the values in (``fit.AVG_CHAR_WIDTH_EM`` for Word's Calibri,
            ``fit.SANS_CHAR_WIDTH_EM`` for the PDF's sans).

    Returns:
        The rows, in order, every value in one size; none for no figure.
    """
    rows = balanced_rows(figures, typography.PAGE_FIGURES_PER_ROW)
    tiles = [(width_pt - typography.PAGE_FIGURE_GAP_PT * (len(row) + 1)) / len(row) for row in rows]
    sizes = [
        _value_size(row, tile - 2 * typography.PAGE_FIGURE_PADDING_PT, narrow_em)
        for row, tile in zip(rows, tiles, strict=True)
    ]
    size = min(sizes, default=0.0)
    return [BandRow(tuple(row), size, tile) for row, tile in zip(rows, tiles, strict=True)]


__all__ = ["BandRow", "plan_band"]
