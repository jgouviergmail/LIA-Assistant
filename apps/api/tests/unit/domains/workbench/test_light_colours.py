"""A colour the person picks is the chromaticity the bridge is sent (ADR-369, Task 9.1).

The screen offers a native colour input (``#rrggbb``, sRGB); the bridge takes
CIE 1931 xy. The conversion is the standard one — sRGB gamma removed, linear
RGB to XYZ (D65), XYZ to xy — and its reference points are the sRGB primaries
and the D65 white point. The way back (xy to ``#rrggbb``) only draws the lamp's
current colour in the input, at full luminance.
"""

from __future__ import annotations

import pytest

from src.domains.workbench.light_colours import hex_to_xy, xy_to_hex

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("colour", "xy"),
    [
        ("#ffffff", (0.3127, 0.3290)),  # D65 white
        ("#FF0000", (0.6400, 0.3300)),  # sRGB red primary
        ("#00ff00", (0.3000, 0.6000)),  # green
        ("#0000ff", (0.1500, 0.0600)),  # blue
    ],
)
def test_the_reference_colours_land_on_their_chromaticity(
    colour: str, xy: tuple[float, float]
) -> None:
    x, y = hex_to_xy(colour)
    assert abs(x - xy[0]) < 0.002 and abs(y - xy[1]) < 0.002


def test_black_has_no_colour_and_reads_as_white() -> None:
    assert hex_to_xy("#000000") == pytest.approx((0.3127, 0.3290), abs=0.002)


@pytest.mark.parametrize("colour", ["#ff8800", "#3366cc", "#22aa55", "#ffffff"])
def test_a_colour_comes_back_as_itself(colour: str) -> None:
    again = hex_to_xy(xy_to_hex(*hex_to_xy(colour)))
    assert again == pytest.approx(hex_to_xy(colour), abs=0.003)


@pytest.mark.parametrize("xy", [(0.0, 0.0), (0.7, -0.1), (1.0, 1.0)])
def test_a_chromaticity_outside_the_triangle_still_draws_a_colour(
    xy: tuple[float, float],
) -> None:
    drawn = xy_to_hex(*xy)
    assert drawn.startswith("#") and len(drawn) == 7
