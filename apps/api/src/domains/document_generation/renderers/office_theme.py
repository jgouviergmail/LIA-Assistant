"""The theme a Word or PowerPoint file carries, in the document's tone (ADR-274 amendment).

What the renderer draws carries its colours explicitly; the THEME is what Office
offers the reader afterwards — a chart or a shape they add picks its colours
from the theme's six accents. A toned document's theme therefore holds the
tone's validated series, so what the reader adds matches what LIA drew. A
document without a tone keeps the template's theme untouched.

Only the six accent colours change, each written as the ``srgbClr`` the
template already uses: nothing else in the part moves, so Office reads the
theme it always read (a measured contract of ``task documents:corpus:measure``).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lxml import etree

_DRAWING = "http://schemas.openxmlformats.org/drawingml/2006/main"
#: The template is ours, but an XML parser still never fetches or expands anything.
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)


def recolor_theme(part: Any, series: Sequence[str]) -> None:
    """Write the series colours as the theme's accents 1-6.

    Args:
        part: The theme part (``/ppt/theme/theme1.xml``, ``/word/theme/theme1.xml``).
        series: Six ``RRGGBB`` colours, in order.

    Raises:
        ValueError: When the part holds no colour scheme with six accents.
    """
    root = etree.fromstring(part.blob, _PARSER)
    scheme = root.find(f".//{{{_DRAWING}}}clrScheme")
    if scheme is None:
        raise ValueError("the theme part has no colour scheme")
    for index, color in enumerate(series, start=1):
        accent = scheme.find(f"{{{_DRAWING}}}accent{index}")
        if accent is None:
            raise ValueError(f"the colour scheme has no accent{index}")
        for child in list(accent):
            accent.remove(child)
        etree.SubElement(accent, f"{{{_DRAWING}}}srgbClr").set("val", color)
    # A generic part keeps its bytes in ``_blob``: python-pptx and python-docx
    # expose no setter, and both serialize the part from it.
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
