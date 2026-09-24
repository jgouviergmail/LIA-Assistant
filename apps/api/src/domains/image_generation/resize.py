"""Preparation of an edit's source image (ADR-305).

The source is read in the orientation the person SEES — a phone photo is stored
sideways with an EXIF tag, and without applying it an edit would choose a
landscape frame for a portrait photo and send the vendor a rotated picture.

It is then fitted within the box its family declares (``ImageFamily.source_box``:
the output size for OpenAI, whose input tokens grow with the area; 2048 px for
Qwen, its documented input ceiling), flattened onto white when it carries
transparency, and encoded as PNG — or JPEG, at the operator's
``IMAGE_GENERATION_ENCODING_QUALITY``, when the PNG exceeds the vendor's byte
limit. The image is never enlarged. Flattening and encoding are the ones the
delivered image uses (``encoding.py``).

Pillow's decode, LANCZOS resampling and encode are CPU-heavy (hundreds of ms on a
multi-megapixel photo): async paths use the ``*_async`` wrappers.
"""

from __future__ import annotations

import asyncio
import io

from PIL import ExifTags, Image, ImageOps

from src.core.config import settings
from src.domains.image_generation.encoding import (
    UNREADABLE_IMAGE_ERRORS,
    encode_image,
    flatten_to_rgb,
)
from src.domains.image_generation.providers.base import SourceImage
from src.domains.image_generation.sizing import ImageSize
from src.infrastructure.media.heif import ensure_heif_support
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# EXIF orientations that turn the stored pixels by a quarter turn.
_QUARTER_TURNS = frozenset({5, 6, 7, 8})
_UNREADABLE_MESSAGE = "The source is not a readable image"


def read_oriented_size(image_bytes: bytes) -> ImageSize:
    """The image's size as displayed, EXIF orientation applied.

    Only the header is read; the pixels are not decoded.

    Args:
        image_bytes: The stored image.

    Returns:
        Width and height as the person sees them.

    Raises:
        ValueError: When the bytes are not an image.
    """
    ensure_heif_support()
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if img.getexif().get(ExifTags.Base.Orientation) in _QUARTER_TURNS:
                width, height = height, width
    except UNREADABLE_IMAGE_ERRORS as exc:
        raise ValueError(_UNREADABLE_MESSAGE) from exc
    return ImageSize(width, height)


def prepare_source_image(image_bytes: bytes, *, box: ImageSize, max_bytes: int) -> SourceImage:
    """Orient, fit, flatten and encode an edit's source image.

    Args:
        image_bytes: The stored image (any Pillow-supported format).
        box: The family's source box for this edit.
        max_bytes: The vendor's limit on an input image.

    Returns:
        The encoded source: PNG, or JPEG when the PNG exceeds ``max_bytes``.

    Raises:
        ValueError: When the bytes are not an image, or the image exceeds
            ``max_bytes`` even as JPEG.
    """
    ensure_heif_support()
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            original = opened.size
            img = flatten_to_rgb(ImageOps.exif_transpose(opened))
    except UNREADABLE_IMAGE_ERRORS as exc:
        raise ValueError(_UNREADABLE_MESSAGE) from exc
    img.thumbnail((box.width, box.height), Image.Resampling.LANCZOS)

    source = SourceImage(data=encode_image(img, "PNG"), mime_type="image/png")
    if len(source.data) > max_bytes:
        quality = settings.image_generation_encoding_quality
        source = SourceImage(
            data=encode_image(img, "JPEG", quality=quality), mime_type="image/jpeg"
        )
    if len(source.data) > max_bytes:
        raise ValueError(f"The source image exceeds {max_bytes} bytes even as JPEG")

    logger.info(
        "image_source_prepared",
        original=f"{original[0]}x{original[1]}",
        prepared=f"{img.size[0]}x{img.size[1]}",
        box=str(box),
        mime_type=source.mime_type,
        size_kb=len(source.data) // 1024,
    )
    return source


async def read_oriented_size_async(image_bytes: bytes) -> ImageSize:
    """Off-loop :func:`read_oriented_size` (HEIC headers can be costly to parse)."""
    return await asyncio.to_thread(read_oriented_size, image_bytes)


async def prepare_source_image_async(
    image_bytes: bytes, *, box: ImageSize, max_bytes: int
) -> SourceImage:
    """Off-loop :func:`prepare_source_image`; always use it on async paths."""
    return await asyncio.to_thread(prepare_source_image, image_bytes, box=box, max_bytes=max_bytes)
