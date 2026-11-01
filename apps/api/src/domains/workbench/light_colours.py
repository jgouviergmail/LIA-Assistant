"""A colour the person picks, as the chromaticity the Hue bridge takes (ADR-369).

The screen's native colour input speaks sRGB (``#rrggbb``); the bridge speaks
CIE 1931 xy. The conversion is the standard one: the sRGB transfer curve
removed, linear RGB to XYZ under the D65 white point, XYZ projected to xy. The
bridge clamps xy to the lamp's own gamut. Black has no chromaticity: it reads
as the white point. The way back draws a lamp's current colour in the input,
at full luminance (brightness is its own control).
"""

from __future__ import annotations

from typing import Final

#: D65, the sRGB white point — where black and a degenerate xy land.
WHITE_POINT: Final = (0.3127, 0.3290)

#: Linear sRGB → XYZ (D65), IEC 61966-2-1.
_TO_XYZ: Final = (
    (0.4124, 0.3576, 0.1805),
    (0.2126, 0.7152, 0.0722),
    (0.0193, 0.1192, 0.9505),
)
#: XYZ → linear sRGB, its inverse.
_TO_RGB: Final = (
    (3.2406, -1.5372, -0.4986),
    (-0.9689, 1.8758, 0.0415),
    (0.0557, -0.2040, 1.0570),
)


def _linear(channel: float) -> float:
    """The sRGB transfer curve, removed."""
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _encoded(channel: float) -> float:
    """The sRGB transfer curve, applied."""
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_xy(colour: str) -> tuple[float, float]:
    """The chromaticity of ``#rrggbb``.

    Args:
        colour: An sRGB colour, ``#`` and six hex digits (checked by the schema).

    Returns:
        CIE 1931 (x, y), four decimals; the white point for black.
    """
    rgb = [_linear(int(colour[index : index + 2], 16) / 255) for index in (1, 3, 5)]
    x_, y_, z_ = (sum(row[i] * rgb[i] for i in range(3)) for row in _TO_XYZ)
    total = x_ + y_ + z_
    if total <= 0:
        return WHITE_POINT
    return round(x_ / total, 4), round(y_ / total, 4)


def xy_to_hex(x: float, y: float) -> str:
    """``#rrggbb`` for a chromaticity, at full luminance (out-of-gamut channels clipped).

    Args:
        x: CIE x.
        y: CIE y; at or below zero the white point is drawn.

    Returns:
        The colour to draw.
    """
    if y <= 0:
        x, y = WHITE_POINT
    xyz = (x / y, 1.0, (1 - x - y) / y)
    rgb = [max(0.0, sum(row[i] * xyz[i] for i in range(3))) for row in _TO_RGB]
    peak = max(rgb) or 1.0
    channels = [round(min(1.0, _encoded(value / peak)) * 255) for value in rgb]
    return "#" + "".join(f"{channel:02x}" for channel in channels)
