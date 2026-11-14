"""The dataviz validator's gates, ported to hold LIA's palettes in CI.

The palettes were CHOSEN with the dataviz skill's own validator
(``validate_palette.js``); this port keeps them validated whenever someone edits
them. Same science, same thresholds: OKLab distances ×100, colour-vision
deficiency simulated with Machado, Oliveira & Fernandes (2009) at severity 1.0,
the light-mode lightness band and chroma floor, WCAG contrast. The port is
calibrated against the validator's own figures in ``test_document_palettes.py``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: OKLCH lightness band of a categorical colour on a light surface.
LIGHT_BAND = (0.43, 0.77)
#: Below this OKLCH chroma a hue reads as grey.
CHROMA_FLOOR = 0.10
#: Worst neighbouring pair under protanopia/deuteranopia (the validator's target).
CVD_TARGET = 8.0
#: Worst neighbouring pair in normal vision (a hard floor).
NORMAL_FLOOR = 15.0
#: A mark against its paper (WCAG 1.4.11).
MARK_CONTRAST = 3.0

_MACHADO: dict[str, tuple[tuple[float, float, float], ...]] = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
}


def _linear(color: str) -> tuple[float, float, float]:
    channels = [int(color[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    return r, g, b


def _oklab(rgb: Sequence[float]) -> tuple[float, float, float]:
    r, g, b = rgb
    l = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)  # noqa: E741
    m = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _simulate(color: str, kind: str) -> tuple[float, float, float]:
    r, g, b = _linear(color)
    rows = _MACHADO[kind]
    simulated = (min(1.0, max(0.0, row[0] * r + row[1] * g + row[2] * b)) for row in rows)
    first, second, third = simulated
    return first, second, third


def delta_e(first: str, second: str, kind: str | None = None) -> float:
    """OKLab distance ×100, in normal vision or under a simulated deficiency."""
    a = _oklab(_simulate(first, kind) if kind else _linear(first))
    b = _oklab(_simulate(second, kind) if kind else _linear(second))
    return 100 * math.dist(a, b)


def lightness_and_chroma(color: str) -> tuple[float, float]:
    """OKLCH L and C."""
    lightness, a, b = _oklab(_linear(color))
    return lightness, math.hypot(a, b)


def worst_cvd(palette: Sequence[str], pairs: Sequence[tuple[int, int]]) -> float:
    """The closest pair under protanopia or deuteranopia."""
    return min(
        delta_e(palette[i], palette[j], kind) for kind in ("protan", "deutan") for i, j in pairs
    )


def worst_normal(palette: Sequence[str], pairs: Sequence[tuple[int, int]]) -> float:
    """The closest pair in normal vision."""
    return min(delta_e(palette[i], palette[j]) for i, j in pairs)


def adjacent(palette: Sequence[str]) -> list[tuple[int, int]]:
    return [(index, index + 1) for index in range(len(palette) - 1)]


def every_pair(count: int) -> list[tuple[int, int]]:
    return [(i, j) for i in range(count) for j in range(i + 1, count)]
