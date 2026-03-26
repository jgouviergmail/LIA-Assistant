"""Image resizing utility for AI image editing.

Resizes source images to the nearest supported dimension template
while preserving aspect ratio. This reduces API costs since larger
images cost more to process.

Supported templates: 1024x1024, 1536x1024, 1024x1536.

Phase: evolution — AI Image Generation (Edit)
Created: 2026-03-25
"""

from __future__ import annotations

import base64
import io

from PIL import Image

from src.core.constants import IMAGE_GENERATION_VALID_SIZES
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Supported dimension templates as (width, height) tuples
_SIZE_TEMPLATES: list[tuple[int, int]] = [
    (int(s.split("x")[0]), int(s.split("x")[1])) for s in IMAGE_GENERATION_VALID_SIZES
]


def _best_template(width: int, height: int) -> tuple[int, int]:
    """Select the template that best matches the source aspect ratio.

    Args:
        width: Source image width.
        height: Source image height.

    Returns:
        (target_width, target_height) from the supported templates.
    """
    src_ratio = width / height if height > 0 else 1.0
    best: tuple[int, int] = _SIZE_TEMPLATES[0]
    best_diff = float("inf")

    for tw, th in _SIZE_TEMPLATES:
        template_ratio = tw / th
        diff = abs(src_ratio - template_ratio)
        if diff < best_diff:
            best_diff = diff
            best = (tw, th)

    return best


def resize_image_b64(
    image_b64: str,
    *,
    max_size: str | None = None,
) -> tuple[str, str]:
    """Resize a base64-encoded image to the nearest supported dimension.

    Opens the image, selects the best-matching template based on aspect
    ratio (or uses ``max_size`` if provided), resizes with LANCZOS
    resampling, and re-encodes as PNG base64.

    Args:
        image_b64: Base64-encoded source image (any PIL-supported format).
        max_size: If provided, force this size (e.g., "1024x1536").
            Otherwise auto-detect from aspect ratio.

    Returns:
        Tuple of (resized_b64, selected_size_str).
        ``selected_size_str`` is e.g. "1024x1536".

    Raises:
        ValueError: If the image cannot be decoded.
    """
    image_bytes = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(image_bytes))

    original_w, original_h = img.size

    if max_size:
        tw, th = (int(d) for d in max_size.split("x"))
    else:
        tw, th = _best_template(original_w, original_h)

    size_str = f"{tw}x{th}"

    # Skip resize if already at or below target
    if original_w <= tw and original_h <= th:
        logger.debug(
            "image_resize_skipped",
            original=f"{original_w}x{original_h}",
            target=size_str,
            reason="already_within_bounds",
        )
        return image_b64, size_str

    # Resize preserving aspect ratio (fit within target box)
    img.thumbnail((tw, th), Image.Resampling.LANCZOS)

    # Convert RGBA to RGB if needed (avoids issues with some APIs)
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background  # type: ignore[assignment]

    # Re-encode as PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resized_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    logger.info(
        "image_resized",
        original=f"{original_w}x{original_h}",
        resized=f"{img.size[0]}x{img.size[1]}",
        target_template=size_str,
        original_size_kb=len(image_bytes) // 1024,
        resized_size_kb=len(buf.getvalue()) // 1024,
    )

    return resized_b64, size_str
