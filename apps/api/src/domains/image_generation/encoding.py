"""How the image domain writes an image: flattening, encoding, delivery (ADR-305).

Every vendor client hands back ONE PNG — that is the client contract. What reaches
the person is written in the format they chose in their settings
(``users.image_generation_output_format``: png, jpeg or webp), converted here,
once, for every vendor: asking each vendor for it would be one path per vendor,
and Qwen answers with a PNG URL whatever it is asked.

A PNG is kept byte for byte. JPEG has no alpha channel, so transparency is
flattened onto white; WebP keeps it. Lossy encodings use the operator's quality
(``IMAGE_GENERATION_ENCODING_QUALITY``), the same one an edit's source is
re-encoded with. The image is already billed when it is converted, so a
conversion that fails delivers the PNG rather than nothing.

Pillow's decode and encode are CPU-heavy: async paths use the ``*_async`` wrapper.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass

from PIL import Image

from src.core.config import settings
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_FLATTEN_BACKGROUND = (255, 255, 255)

#: What Pillow raises on bytes it cannot decode: not an image, a truncated file,
#: or a decompression bomb.
UNREADABLE_IMAGE_ERRORS: tuple[type[Exception], ...] = (OSError, Image.DecompressionBombError)
#: What a conversion can raise besides: an encoder this Pillow build lacks
#: (``KeyError``) or a mode it refuses (``ValueError``).
_CONVERSION_ERRORS: tuple[type[Exception], ...] = (*UNREADABLE_IMAGE_ERRORS, KeyError, ValueError)


@dataclass(frozen=True)
class OutputFormat:
    """One format a person may receive their images in.

    Attributes:
        pillow_format: Pillow's name for the encoder.
        mime_type: What the attachment is served as.
        extension: The stored file's extension.
    """

    pillow_format: str
    mime_type: str
    extension: str


#: Keyed by the preference's vocabulary (``IMAGE_GENERATION_VALID_FORMATS``); a
#: test holds the two equal.
OUTPUT_FORMATS: dict[str, OutputFormat] = {
    "png": OutputFormat("PNG", "image/png", "png"),
    "jpeg": OutputFormat("JPEG", "image/jpeg", "jpg"),
    "webp": OutputFormat("WEBP", "image/webp", "webp"),
}


@dataclass(frozen=True)
class DeliveredImage:
    """An image as it is stored and served.

    Attributes:
        data: The encoded image.
        mime_type: Its media type.
        extension: Its file extension.
    """

    data: bytes
    mime_type: str
    extension: str


def flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white; convert any other mode to RGB."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, _FLATTEN_BACKGROUND)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return img if img.mode == "RGB" else img.convert("RGB")


def encode_image(img: Image.Image, fmt: str, **params: int) -> bytes:
    """Encode ``img`` in Pillow's ``fmt`` with the given encoder parameters."""
    buf = io.BytesIO()
    img.save(buf, format=fmt, **params)
    return buf.getvalue()


def _for_webp(img: Image.Image) -> Image.Image:
    """RGB or RGBA — the modes the WebP encoder takes — keeping any alpha."""
    if img.mode in ("RGB", "RGBA"):
        return img
    has_alpha = img.mode in ("LA", "PA") or "transparency" in img.info
    return img.convert("RGBA" if has_alpha else "RGB")


def encode_for_delivery(png: bytes, output_format: str) -> DeliveredImage:
    """Write a vendor's PNG in the format the person chose.

    Args:
        png: The image a client returned.
        output_format: The person's preference (``png``, ``jpeg`` or ``webp``).

    Returns:
        The image to store: the PNG itself, or its conversion. An unknown format
        or a conversion that fails delivers the PNG, logged.
    """
    as_png = DeliveredImage(png, OUTPUT_FORMATS["png"].mime_type, OUTPUT_FORMATS["png"].extension)
    target = OUTPUT_FORMATS.get(output_format)
    if target is None:
        logger.warning("image_output_format_unknown", output_format=output_format)
        return as_png
    if target.pillow_format == "PNG":
        return as_png
    quality = settings.image_generation_encoding_quality
    try:
        with Image.open(io.BytesIO(png)) as img:
            img.load()
            converted = flatten_to_rgb(img) if target.pillow_format == "JPEG" else _for_webp(img)
            data = encode_image(converted, target.pillow_format, quality=quality)
    except _CONVERSION_ERRORS as exc:
        logger.warning(
            "image_output_conversion_failed",
            output_format=output_format,
            error_type=type(exc).__name__,
        )
        return as_png
    return DeliveredImage(data, target.mime_type, target.extension)


async def encode_for_delivery_async(png: bytes, output_format: str) -> DeliveredImage:
    """Off-loop :func:`encode_for_delivery`; always use it on async paths."""
    return await asyncio.to_thread(encode_for_delivery, png, output_format)
