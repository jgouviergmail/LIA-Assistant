"""Shared metadata chips, isolated from card orchestration."""

from src.domains.agents.display.escaping import escape_html


def render_chip(
    text: str,
    variant: str = "",
    icon_name: str = "",
) -> str:
    """Render a single chip (inline metadata tag with optional icon).

    Args:
        text: Chip text content
        variant: Color variant (green, amber, red, indigo, time, stars, thread, attach, allday)
        icon_name: Optional Material Symbols icon name

    Returns:
        HTML for a lia-chip span
    """
    variant_class = f" lia-chip--{variant}" if variant else ""
    icon_html = (
        f'<span class="material-symbols-outlined">{escape_html(icon_name)}</span>'
        if icon_name
        else ""
    )
    return f'<span class="lia-chip{variant_class}">{icon_html}{escape_html(text)}</span>'


def render_chip_stars(rating: float, count: int = 0) -> str:
    """Render a star-rating chip with filled/empty stars.

    Args:
        rating: Rating value (0-5). Accepts the numeric STRING form too — JSON
            providers and MCP results commonly send ``"4.5"`` — because
            ``int("4.5")`` raises and the caller's exception boundary would then
            drop every card of the answer, not just this chip.
        count: Number of reviews (0 to hide count)

    Returns:
        HTML for a lia-chip--stars chip
    """
    try:
        numeric_rating = float(rating)
    except TypeError, ValueError:
        return ""

    full = max(0, min(5, int(numeric_rating)))
    stars_html = "".join(
        '<span class="material-symbols-outlined" aria-hidden="true">star</span>'
        for _ in range(full)
    )
    empty_html = "".join(
        '<span class="material-symbols-outlined lia-chip__star-empty" aria-hidden="true">star</span>'
        for _ in range(5 - full)
    )
    count_text = f" {numeric_rating:g}/5"
    if count:
        count_text += f" ({count})"
    return f'<span class="lia-chip lia-chip--stars">{stars_html}{empty_html}{escape_html(count_text)}</span>'


def render_chip_row(
    chips_html: str,
    separator_pos: str = "",
) -> str:
    """Render a row of chips with optional separators.

    Args:
        chips_html: Pre-built HTML of lia-chip elements
        separator_pos: Where to add border separators:
            "" = no separator, "top", "bottom", "both"

    Returns:
        HTML for a lia-chip-row div
    """
    sep_class = f" lia-chip-row--sep-{separator_pos}" if separator_pos else ""
    return f'<div class="lia-chip-row{sep_class}">{chips_html}</div>'
