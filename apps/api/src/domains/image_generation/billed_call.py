"""One billed call to the configured image model — the door image producers share (ADR-305).

The image tools and a document's illustrations run the same act: open the
configured model's client on this loop, ask it, and record what the vendor
BILLED (ADR-272) — an image delivered, or an image produced and lost on the way
(``ImageDeliveryError``). A refusal, a throttle or a timeout bills nothing. A
failure is re-raised typed: each caller says it in its own words, the tool to
the model, a document in its report.

A cancelled call records nothing: whether the vendor finished is unknown, and a
generation whose outcome is unknown is neither relaunched nor guessed (ADR-221).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from src.domains.image_generation.client import create_image_client
from src.domains.image_generation.options_cache import ModelOptions
from src.domains.image_generation.providers.base import (
    ImageDeliveryError,
    ImageGenerationClient,
    ImageResult,
)
from src.domains.image_generation.tracker import track_image_generation_call

#: What to ask the configured model's client.
ProviderCall = Callable[[ImageGenerationClient], Awaitable[ImageResult]]
#: Records the cost of a call the vendor billed, given its duration in milliseconds.
Bill = Callable[[float], None]


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


async def call_billed(options: ModelOptions, call: ProviderCall, *, bill: Bill) -> ImageResult:
    """Run one vendor call on the configured model's client, and bill what it cost.

    Args:
        options: The configured model's offer; its provider picks the client.
        call: What to ask the client.
        bill: Records the call's cost; invoked once for every image the vendor
            billed — delivered, or produced and lost on the way.

    Returns:
        The image.

    Raises:
        ImageGenerationError: The client's typed failure, re-raised after the
            bill when the vendor billed it.
    """
    started = time.monotonic()
    try:
        async with create_image_client(options.provider) as client:
            result = await call(client)
    except ImageDeliveryError:
        bill(_elapsed_ms(started))
        raise
    bill(_elapsed_ms(started))
    return result


async def generate_billed(
    options: ModelOptions, *, prompt: str, quality: str, size: str
) -> ImageResult:
    """Generate one image, billed as one image of its quality and size.

    Args:
        options: The configured model's offer.
        prompt: What the vendor receives — and what the bill records.
        quality: A quality the model offers.
        size: A size the model offers.

    Returns:
        The image.

    Raises:
        ImageGenerationError: The client's typed failure.
    """
    return await call_billed(
        options,
        lambda client: client.generate(
            prompt=prompt, model=options.model, quality=quality, size=size
        ),
        bill=lambda duration_ms: track_image_generation_call(
            model=options.model,
            quality=quality,
            size=size,
            image_count=1,
            prompt=prompt,
            duration_ms=duration_ms,
        ),
    )


__all__ = ["Bill", "ProviderCall", "call_billed", "generate_billed"]
