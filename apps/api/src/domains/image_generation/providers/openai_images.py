"""OpenAI GPT Image client: the Images API for both generation and edit (ADR-305).

The edit used to go through the Responses API, whose ``image_generation`` tool
runs its OWN default model (``gpt-image-1``) unless told otherwise — the cost was
recorded against the configured model while another one ran, and the TEXT model
orchestrating the tool spent tokens nobody recorded. ``images.edit`` takes the
configured model and the reference image directly: the model that runs is the
model that is priced.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Literal

from openai.types import Image, ImagesResponse

from src.domains.image_generation.providers.base import (
    ImageGenerationClient,
    ImageGenerationError,
    ImageResult,
    SourceImage,
    log_provider_call,
)
from src.domains.image_generation.providers.openai_sdk import (
    openai_sdk_client,
    require_provider_key,
    vendor_errors,
)

_PROVIDER = "openai"
_SOURCE_FILENAMES: dict[str, str] = {"image/png": "source.png", "image/jpeg": "source.jpg"}

OpenAIImageQuality = Literal["low", "medium", "high"]

# The SDK types ``quality`` as a Literal. The family (``OPENAI_GPT_IMAGE``) has
# already validated the value; this table narrows it without a cast, and a test
# pins it to the family's vocabulary.
_QUALITIES: dict[str, OpenAIImageQuality] = {"low": "low", "medium": "medium", "high": "high"}


def _quality(value: str) -> OpenAIImageQuality:
    """Narrow a validated quality to the SDK's Literal.

    Raises:
        ImageGenerationError: When ``value`` is not an OpenAI GPT Image quality.
    """
    narrowed = _QUALITIES.get(value)
    if narrowed is None:
        raise ImageGenerationError(f"Quality {value!r} is not an OpenAI GPT Image quality")
    return narrowed


class OpenAIImageClient(ImageGenerationClient):
    """OpenAI GPT Image models through the Images API."""

    def __init__(self) -> None:
        """Build the SDK client with the chat factory's key and base URL.

        Raises:
            ImageProviderNotConfiguredError: When no OpenAI key is configured.
        """
        self._client = openai_sdk_client(_PROVIDER, require_provider_key(_PROVIDER))

    async def generate(self, *, prompt: str, model: str, quality: str, size: str) -> ImageResult:
        """Generate one image with ``images.generate``.

        Args:
            prompt: What to draw.
            model: The configured GPT Image model.
            quality: ``low``, ``medium`` or ``high``.
            size: One of the family's three sizes.

        Returns:
            The generated PNG.

        Raises:
            ImageGenerationError: When the vendor refuses or answers without an image.
        """
        with vendor_errors():
            response = await self._client.images.generate(
                model=model,
                prompt=prompt,
                n=1,
                size=size,
                quality=_quality(quality),
                output_format="png",
            )
        return self._single_image(response, action="generate", model=model, size=size)

    async def edit(
        self, *, prompt: str, source: SourceImage, model: str, quality: str, size: str
    ) -> ImageResult:
        """Edit with ``images.edit`` on the configured model (no mask).

        Args:
            prompt: The modification to make.
            source: The reference image, fitted within the output size.
            model: The configured GPT Image model.
            quality: ``low``, ``medium`` or ``high``.
            size: The output size, chosen for the source's proportions.

        Returns:
            The edited PNG.

        Raises:
            ImageGenerationError: When the vendor refuses or answers without an image.
        """
        filename = _SOURCE_FILENAMES.get(source.mime_type, "source.png")
        with vendor_errors():
            response = await self._client.images.edit(
                model=model,
                image=(filename, source.data, source.mime_type),
                prompt=prompt,
                n=1,
                size=size,
                quality=_quality(quality),
                output_format="png",
            )
        return self._single_image(response, action="edit", model=model, size=size)

    async def aclose(self) -> None:
        """Close the SDK's HTTP client."""
        await self._client.close()

    @staticmethod
    def _single_image(
        response: ImagesResponse, *, action: str, model: str, size: str
    ) -> ImageResult:
        """Decode the first image of an Images API answer.

        Args:
            response: The SDK's answer.
            action: ``generate`` or ``edit``, for the call's log line.
            model: The model that was asked.
            size: The size that was asked.

        Returns:
            The decoded PNG and the vendor's revised prompt, if any.

        Raises:
            ImageGenerationError: When the answer carries no base64 image.
        """
        images: Sequence[Image] = response.data or ()
        encoded = images[0].b64_json if images else None
        if not encoded:
            raise ImageGenerationError("OpenAI returned no image data")
        png = base64.b64decode(encoded)
        # ``_request_id`` is the SDK's documented accessor for the id support asks for.
        log_provider_call(
            provider=_PROVIDER,
            action=action,
            model=model,
            size=size,
            request_id=response._request_id,
            result_bytes=len(png),
        )
        return ImageResult(
            png=png, model=model, provider=_PROVIDER, revised_prompt=images[0].revised_prompt
        )
