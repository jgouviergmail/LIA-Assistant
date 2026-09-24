"""Tests for the edit's source-image preparation (ADR-305, audit wave 3 item A6).

The source is read in the orientation the person sees (EXIF applied), fitted within
its family's box, and encoded under the vendor's byte limit. Pillow's decode,
LANCZOS and encode stay off the event loop.
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from src.domains.image_generation.resize import (
    prepare_source_image,
    prepare_source_image_async,
    read_oriented_size,
    read_oriented_size_async,
)
from src.domains.image_generation.sizing import ImageSize
from tests.helpers.event_loop import assert_workload_off_loop

# Threshold for the event-loop stall assertion. A synchronous preparation of the
# large test image takes several hundred ms; off-loop it stays far below this.
_MAX_ALLOWED_STALL_SECONDS = 0.15
_EXIF_ORIENTATION = 0x0112
_ROTATE_90_CW = 6


def _encode(img: Image.Image, fmt: str = "PNG", **params: object) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format=fmt, **params)
    return buf.getvalue()


def _image(width: int, height: int, mode: str = "RGB") -> bytes:
    color = (200, 100, 50) if mode == "RGB" else (200, 100, 50, 128)
    return _encode(Image.new(mode, (width, height), color))


def _phone_photo(width: int, height: int) -> bytes:
    """A JPEG stored sideways with an EXIF tag telling viewers to rotate it."""
    exif = Image.Exif()
    exif[_EXIF_ORIENTATION] = _ROTATE_90_CW
    return _encode(Image.new("RGB", (width, height), (10, 20, 30)), "JPEG", exif=exif)


def _noise(width: int, height: int) -> bytes:
    """Incompressible pixels: the worst case for PNG size and CPU time."""
    return _encode(Image.frombytes("RGB", (width, height), os.urandom(width * height * 3)))


def _open(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


@pytest.mark.unit
class TestReadOrientedSize:
    """The proportions an edit keeps are the ones the person sees."""

    def test_reads_plain_dimensions(self) -> None:
        assert read_oriented_size(_image(1600, 900)) == ImageSize(1600, 900)

    def test_a_rotated_phone_photo_reads_as_it_is_displayed(self) -> None:
        """Stored 400x300 with a 90° tag, it is a PORTRAIT photo."""
        assert read_oriented_size(_phone_photo(400, 300)) == ImageSize(300, 400)

    async def test_async_matches_sync(self) -> None:
        data = _phone_photo(400, 300)
        assert await read_oriented_size_async(data) == read_oriented_size(data)


@pytest.mark.unit
class TestPrepareSourceImage:
    """Fitted within the box, oriented, flattened, under the byte limit."""

    def test_a_large_image_is_fitted_within_the_box_keeping_its_proportions(self) -> None:
        source = prepare_source_image(
            _image(3000, 2000), box=ImageSize(1536, 1024), max_bytes=10_000_000
        )
        assert source.mime_type == "image/png"
        assert _open(source.data).size == (1536, 1024)

    def test_a_small_image_is_never_enlarged(self) -> None:
        source = prepare_source_image(
            _image(512, 512), box=ImageSize(2048, 2048), max_bytes=10_000_000
        )
        assert _open(source.data).size == (512, 512)

    def test_the_rotation_is_applied_before_sending(self) -> None:
        source = prepare_source_image(
            _phone_photo(400, 300), box=ImageSize(2048, 2048), max_bytes=10_000_000
        )
        assert _open(source.data).size == (300, 400)

    def test_transparency_is_flattened_to_rgb(self) -> None:
        source = prepare_source_image(
            _image(800, 800, mode="RGBA"), box=ImageSize(1024, 1024), max_bytes=10_000_000
        )
        assert _open(source.data).mode == "RGB"

    def test_a_png_over_the_vendor_limit_is_sent_as_jpeg(self) -> None:
        noise = _noise(1000, 1000)
        assert len(noise) > 2_000_000
        source = prepare_source_image(noise, box=ImageSize(2048, 2048), max_bytes=2_000_000)
        assert source.mime_type == "image/jpeg"
        assert len(source.data) <= 2_000_000
        assert _open(source.data).format == "JPEG"

    def test_an_image_the_vendor_cannot_take_even_as_jpeg_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            prepare_source_image(_noise(1000, 1000), box=ImageSize(2048, 2048), max_bytes=10_000)

    def test_something_that_is_not_an_image_is_refused(self) -> None:
        with pytest.raises(ValueError):
            prepare_source_image(b"%PDF-1.7", box=ImageSize(1024, 1024), max_bytes=10_000_000)


@pytest.mark.unit
class TestPrepareSourceImageAsync:
    """The async wrapper keeps the event loop responsive."""

    async def test_matches_sync_result(self) -> None:
        data = _image(2048, 1536)
        box = ImageSize(1536, 1024)
        assert await prepare_source_image_async(
            data, box=box, max_bytes=10_000_000
        ) == prepare_source_image(data, box=box, max_bytes=10_000_000)

    async def test_does_not_block_event_loop(self) -> None:
        """A CPU-heavy preparation must not stall concurrent coroutines."""
        data = _noise(3000, 3000)
        box = ImageSize(1024, 1024)

        source = await assert_workload_off_loop(
            lambda: prepare_source_image_async(data, box=box, max_bytes=50_000_000),
            blocking_baseline=lambda: prepare_source_image(data, box=box, max_bytes=50_000_000),
            absolute_threshold_seconds=_MAX_ALLOWED_STALL_SECONDS,
            context="prepare_source_image",
        )

        assert _open(source.data).size == (1024, 1024)
