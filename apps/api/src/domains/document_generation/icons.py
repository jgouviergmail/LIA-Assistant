"""The pictograms a generated document may carry: a closed set, drawn here (ADR-274).

The writer names an icon from ``schemas.SLIDE_ICONS``; the renderer draws it
from the geometry vendored in ``lucide_icons.json`` — lucide-react, ISC, the
notice travelling inside the file and credited in NOTICE.md; refreshed by
``scripts/document_generation/vendor_lucide_icons.mjs``. Nothing is fetched:
the geometry is read once per process, each drawing is rasterized once per
name and colour, and the cache is bounded.

An unknown name draws nothing: a pictogram is decoration, never worth a failed
document (ADR-269).
"""

from __future__ import annotations

import json
import re
from functools import cache, lru_cache
from pathlib import Path
from xml.sax.saxutils import quoteattr

from src.domains.document_generation.raster import svg_to_png

#: The vendored geometry, next to this module.
ICON_FILE = Path(__file__).with_name("lucide_icons.json")
#: The SVG elements the vendored set uses and the rasterizer draws.
DRAWN_ELEMENTS: frozenset[str] = frozenset(
    {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
)
#: A pictogram is drawn at this width: crisp at 1.4 in on a 200 dpi projection.
ICON_RASTER_PX = 256
#: Distinct (name, colour) drawings kept per process: 28 names x a few inks.
ICON_CACHE_SIZE = 128

_HEX_COLOR = re.compile(r"[0-9A-Fa-f]{6}")
#: Lucide's own drawing attributes: a 24-unit grid stroked at 2 with round ends.
_SVG_OPEN = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
    'fill="none" stroke="#{color}" stroke-width="2" stroke-linecap="round" '
    'stroke-linejoin="round">'
)


@cache
def _geometry() -> dict[str, list[tuple[str, dict[str, str]]]]:
    """name -> its SVG elements, read from the vendored file once per process."""
    vendored = json.loads(ICON_FILE.read_text(encoding="utf-8"))
    return {
        name: [(str(tag), dict(attributes)) for tag, attributes in elements]
        for name, elements in vendored["icons"].items()
    }


def icon_names() -> frozenset[str]:
    """Every name the vendored set can draw."""
    return frozenset(_geometry())


def icon_svg(name: str, color: str) -> bytes | None:
    """The icon as an SVG document stroked in ``color``.

    Args:
        name: A Lucide name from the vendored set.
        color: Six hexadecimal digits, without ``#``.

    Returns:
        The SVG bytes, or ``None`` when the set has no such icon.

    Raises:
        ValueError: When ``color`` is not six hexadecimal digits — it is written
            into an attribute, so nothing else may reach it.
    """
    if not _HEX_COLOR.fullmatch(color):
        raise ValueError(f"not a hex colour: {color!r}")
    elements = _geometry().get(name)
    if elements is None:
        return None
    body = "".join(
        f"<{tag} "
        + " ".join(f"{key}={quoteattr(value)}" for key, value in attributes.items())
        + "/>"
        for tag, attributes in elements
    )
    return (_SVG_OPEN.format(color=color) + body + "</svg>").encode("utf-8")


@lru_cache(maxsize=ICON_CACHE_SIZE)
def icon_png(name: str, color: str) -> bytes | None:
    """The icon as a transparent PNG, ``ICON_RASTER_PX`` wide, drawn once.

    Args:
        name: A Lucide name from the vendored set.
        color: Six hexadecimal digits, without ``#``.

    Returns:
        The PNG bytes, or ``None`` when the set has no such icon.
    """
    svg = icon_svg(name, color)
    if svg is None:
        return None
    return svg_to_png(svg, width_px=ICON_RASTER_PX, transparent=True)


__all__ = [
    "DRAWN_ELEMENTS",
    "ICON_CACHE_SIZE",
    "ICON_FILE",
    "ICON_RASTER_PX",
    "icon_names",
    "icon_png",
    "icon_svg",
]
