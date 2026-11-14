"""The pictograms a deck may carry: vendored, drawn in the asked colour, cached (ADR-274)."""

from __future__ import annotations

import json

import pytest

from src.domains.document_generation import icons
from src.domains.document_generation.raster import pymupdf
from src.domains.document_generation.schemas import SLIDE_ICONS

pytestmark = pytest.mark.unit

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _pixels(png: bytes) -> list[tuple[int, int, int, int]]:
    pixmap = pymupdf().Pixmap(png)
    assert pixmap.n == 4, "the pictogram keeps its alpha channel"
    samples = pixmap.samples
    return [
        (samples[i], samples[i + 1], samples[i + 2], samples[i + 3])
        for i in range(0, len(samples), 4)
    ]


class TestTheVendoredSet:
    def test_the_file_holds_exactly_the_published_vocabulary(self) -> None:
        assert set(icons.icon_names()) == set(SLIDE_ICONS)

    def test_the_file_says_where_it_comes_from_and_carries_its_licence(self) -> None:
        vendored = json.loads(icons.ICON_FILE.read_text(encoding="utf-8"))
        assert vendored["source"].startswith("lucide-react@")
        assert "ISC License" in vendored["licence"]
        assert "Lucide Icons and Contributors" in vendored["licence"]

    def test_every_element_is_one_the_rasterizer_draws(self) -> None:
        vendored = json.loads(icons.ICON_FILE.read_text(encoding="utf-8"))
        for name, elements in vendored["icons"].items():
            assert elements, name
            for tag, geometry in elements:
                assert tag in icons.DRAWN_ELEMENTS, (name, tag)
                assert "key" not in geometry, (name, "React's key is not geometry")


class TestTheDrawing:
    @pytest.mark.parametrize("name", SLIDE_ICONS)
    def test_every_icon_is_drawn_in_the_asked_colour_on_a_clear_ground(self, name: str) -> None:
        png = icons.icon_png(name, "1C5CAB")

        assert png is not None and png.startswith(_PNG_MAGIC)
        pixels = _pixels(png)
        opaque = {rgb[:3] for rgb in pixels if rgb[3] == 255}
        assert opaque == {(0x1C, 0x5C, 0xAB)}, name
        assert any(alpha == 0 for *_rgb, alpha in pixels), name

    def test_the_size_is_the_raster_size(self) -> None:
        png = icons.icon_png("target", "1A1A1A")
        assert png is not None
        pixmap = pymupdf().Pixmap(png)
        assert (pixmap.width, pixmap.height) == (icons.ICON_RASTER_PX, icons.ICON_RASTER_PX)

    @pytest.mark.parametrize("name", ["", "unicorn", "Target", "../target"])
    def test_a_name_outside_the_set_draws_nothing(self, name: str) -> None:
        assert icons.icon_png(name, "1C5CAB") is None

    @pytest.mark.parametrize("color", ["#1C5CAB", "1C5CA", "red", '1C5CAB" onload="x'])
    def test_a_colour_that_is_not_six_hex_digits_is_refused(self, color: str) -> None:
        with pytest.raises(ValueError):
            icons.icon_svg("target", color)

    def test_a_drawing_is_made_once_per_name_and_colour(self) -> None:
        icons.icon_png.cache_clear()
        first = icons.icon_png("rocket", "199E70")
        second = icons.icon_png("rocket", "199E70")
        info = icons.icon_png.cache_info()

        assert first is second
        assert (info.hits, info.misses) == (1, 1)
        assert info.maxsize == icons.ICON_CACHE_SIZE
