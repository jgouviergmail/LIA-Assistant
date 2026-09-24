"""Unit tests for the image a person receives, in the format they chose (ADR-305)."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from structlog.testing import capture_logs

from src.core.config import settings
from src.core.constants import IMAGE_GENERATION_VALID_FORMATS
from src.domains.image_generation.encoding import (
    OUTPUT_FORMATS,
    encode_for_delivery,
    encode_for_delivery_async,
)

pytestmark = pytest.mark.unit


def _png(mode: str = "RGBA", size: tuple[int, int] = (64, 48)) -> bytes:
    """A PNG whose left half is fully transparent red and right half opaque blue."""
    img = Image.new(mode, size, (0, 0, 255, 255) if mode == "RGBA" else (0, 0, 255))
    if mode == "RGBA":
        for x in range(size[0] // 2):
            for y in range(size[1]):
                img.putpixel((x, y), (255, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def _pixel(img: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    value = img.getpixel(xy)
    assert isinstance(value, tuple)
    return value


class TestTheVocabulary:
    def test_every_format_a_person_may_choose_is_delivered(self) -> None:
        """The preference's validator and the encoder table name ONE vocabulary."""
        assert set(OUTPUT_FORMATS) == set(IMAGE_GENERATION_VALID_FORMATS)


class TestEncodeForDelivery:
    def test_a_png_is_kept_byte_for_byte(self) -> None:
        png = _png()
        delivered = encode_for_delivery(png, "png")
        assert delivered.data is png
        assert (delivered.mime_type, delivered.extension) == ("image/png", "png")

    def test_jpeg_flattens_transparency_onto_white(self) -> None:
        delivered = encode_for_delivery(_png(), "jpeg")

        img = _open(delivered.data)
        assert (img.format, img.mode) == ("JPEG", "RGB")
        assert (delivered.mime_type, delivered.extension) == ("image/jpeg", "jpg")
        # The transparent half became white, not black nor red.
        assert all(channel > 240 for channel in _pixel(img, (5, 5)))

    def test_webp_keeps_transparency(self) -> None:
        delivered = encode_for_delivery(_png(), "webp")

        img = _open(delivered.data)
        assert (img.format, img.mode) == ("WEBP", "RGBA")
        assert (delivered.mime_type, delivered.extension) == ("image/webp", "webp")
        assert _pixel(img, (5, 5))[3] == 0

    def test_an_opaque_png_becomes_an_opaque_webp(self) -> None:
        img = _open(encode_for_delivery(_png(mode="RGB"), "webp").data)
        assert img.mode == "RGB"

    def test_the_operator_s_quality_is_the_encoder_s(self, monkeypatch: pytest.MonkeyPatch) -> None:
        photo = Image.effect_noise((256, 256), 64).convert("RGB")
        buf = io.BytesIO()
        photo.save(buf, format="PNG")
        png = buf.getvalue()

        monkeypatch.setattr(settings, "image_generation_encoding_quality", 95)
        fine = encode_for_delivery(png, "jpeg")
        monkeypatch.setattr(settings, "image_generation_encoding_quality", 20)
        coarse = encode_for_delivery(png, "jpeg")

        assert len(coarse.data) < len(fine.data)

    def test_an_image_that_cannot_be_converted_is_delivered_as_png(self) -> None:
        """It was billed: the person gets it in PNG rather than not at all."""
        broken = b"\x89PNG\r\n\x1a\n" + b"not really"
        with capture_logs() as logs:
            delivered = encode_for_delivery(broken, "webp")

        assert delivered.data is broken and delivered.mime_type == "image/png"
        assert [e["event"] for e in logs] == ["image_output_conversion_failed"]

    def test_an_unknown_format_is_delivered_as_png_and_said(self) -> None:
        png = _png()
        with capture_logs() as logs:
            delivered = encode_for_delivery(png, "tiff")

        assert delivered.data is png and delivered.extension == "png"
        assert [e["event"] for e in logs] == ["image_output_format_unknown"]

    async def test_the_async_wrapper_converts_off_the_loop(self) -> None:
        delivered = await encode_for_delivery_async(_png(), "jpeg")
        assert _open(delivered.data).format == "JPEG"
