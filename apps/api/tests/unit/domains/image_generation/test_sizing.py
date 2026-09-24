"""Unit tests for the image-size arithmetic shared by every family (ADR-305)."""

from __future__ import annotations

import pytest

from src.domains.image_generation.sizing import (
    ImageSize,
    closest_by_aspect,
    closest_in_orientation,
    is_well_formed_size,
)


@pytest.mark.unit
class TestImageSize:
    """Parsing and derived properties."""

    def test_parses_the_wxh_notation_both_vendors_use(self) -> None:
        size = ImageSize.parse("1536x1024")
        assert (size.width, size.height) == (1536, 1024)
        assert str(size) == "1536x1024"
        assert size.area == 1_572_864

    @pytest.mark.parametrize(
        "raw",
        # ``$`` alone matches before a trailing newline: a size stored with one
        # would key the price cache differently from the offer it is shown in.
        ["", "1024", "1024*1024", "0x1024", "axb", "1024x", "-5x10", "1024x1024\n"],
    )
    def test_refuses_what_is_not_a_positive_wxh(self, raw: str) -> None:
        with pytest.raises(ValueError):
            ImageSize.parse(raw)
        assert not is_well_formed_size(raw)

    @pytest.mark.parametrize(
        ("raw", "orientation"),
        [
            ("1024x1024", "square"),
            ("1536x1024", "landscape"),
            ("1024x1536", "portrait"),
            ("2448x1632", "landscape"),
        ],
    )
    def test_orientation(self, raw: str, orientation: str) -> None:
        assert ImageSize.parse(raw).orientation == orientation


@pytest.mark.unit
class TestClosestByAspect:
    """An edit keeps the source's proportions."""

    def test_picks_the_nearest_proportion(self) -> None:
        candidates = [ImageSize.parse(s) for s in ("1024x1024", "1536x1024", "1024x1536")]
        photo_4_3 = ImageSize(4000, 3000)
        assert closest_by_aspect(candidates, photo_4_3) == ImageSize(1536, 1024)

    def test_a_portrait_never_lands_on_a_landscape(self) -> None:
        candidates = [ImageSize.parse(s) for s in ("1024x1024", "1536x1024", "1024x1536")]
        assert closest_by_aspect(candidates, ImageSize(900, 1600)) == ImageSize(1024, 1536)

    def test_a_tie_resolves_to_the_smaller_area(self) -> None:
        candidates = [ImageSize(2048, 2048), ImageSize(1024, 1024)]
        assert closest_by_aspect(candidates, ImageSize(500, 500)) == ImageSize(1024, 1024)

    def test_a_portrait_source_mirrors_the_landscape_choice(self) -> None:
        """Proportions are compared on log ratios: 2:1 is as far from 1:1 as from 4:1.

        A linear difference would send a 2:1 source to the square and a 1:2 source
        to the extreme — one shape of photo edited differently from its mirror.
        """
        wide = closest_by_aspect(
            [ImageSize(1024, 1024), ImageSize(1600, 400)], ImageSize(2000, 1000)
        )
        tall = closest_by_aspect(
            [ImageSize(1024, 1024), ImageSize(400, 1600)], ImageSize(1000, 2000)
        )
        assert tall == ImageSize(wide.height, wide.width)


@pytest.mark.unit
class TestClosestInOrientation:
    """A stored size the model does not offer keeps its orientation."""

    def test_keeps_the_orientation_and_the_nearest_area(self) -> None:
        offered = [
            ImageSize.parse(s)
            for s in ("1024x1024", "1536x1024", "1024x1536", "2048x2048", "2448x1632", "1632x2448")
        ]
        assert closest_in_orientation(offered, ImageSize(1200, 1800)) == ImageSize(1024, 1536)
        assert closest_in_orientation(offered, ImageSize(2400, 1600)) == ImageSize(2448, 1632)

    def test_falls_back_to_the_nearest_proportion_when_the_orientation_is_missing(self) -> None:
        offered = [ImageSize(1024, 1024), ImageSize(1536, 1024)]
        assert closest_in_orientation(offered, ImageSize(1024, 1536)) == ImageSize(1024, 1024)

    def test_refuses_an_empty_offer(self) -> None:
        with pytest.raises(ValueError):
            closest_in_orientation([], ImageSize(1024, 1024))
