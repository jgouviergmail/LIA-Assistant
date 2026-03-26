"""TrackingContext helper for image generation cost recording.

Provides a simple function to record image generation costs
into the current request's TrackingContext via the current_tracker ContextVar.

Follows the same pattern as track_google_api_call() in
src/domains/connectors/clients/google_api_tracker.py.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from src.core.context import current_tracker
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def track_image_generation_call(
    model: str,
    quality: str,
    size: str,
    image_count: int,
    prompt: str,
    duration_ms: float = 0.0,
) -> None:
    """Record an image generation call in the current TrackingContext.

    This is a synchronous function that uses the pre-loaded pricing cache
    via TrackingContext.record_image_generation_call().

    Safe to call outside chat context (e.g., direct API usage):
    silently no-ops if no tracker is active.

    Args:
        model: Image generation model used (e.g., "gpt-image-1").
        quality: Quality level used (e.g., "medium").
        size: Image dimensions used (e.g., "1024x1024").
        image_count: Number of images generated.
        prompt: Original prompt text (truncated for audit).
        duration_ms: API call duration in milliseconds.
    """
    tracker = current_tracker.get()
    if tracker is not None:
        tracker.record_image_generation_call(
            model=model,
            quality=quality,
            size=size,
            image_count=image_count,
            prompt_preview=prompt,
            duration_ms=duration_ms,
        )
    else:
        logger.debug(
            "image_generation_tracking_skipped_no_tracker",
            model=model,
            quality=quality,
            size=size,
            image_count=image_count,
        )
