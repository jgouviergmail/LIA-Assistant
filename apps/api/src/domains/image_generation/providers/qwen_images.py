"""Qwen Image client: the workspace's OpenAI-compatible endpoint (ADR-305).

Text to image and image to image share ``/images/generations``; an edit adds the
reference image as a data URI in the ``image`` extension field. The answer is a
URL valid 24 hours, downloaded at once (``result_download``).

The quality is not a vendor parameter: the price depends on the output area's
tier, which the requested size decides. The vendor reports the tier it billed
(``usage.output_image_type``); a disagreement with the model family's is logged,
so the day the vendor moves its threshold the log says so before the invoices do.
"""

from __future__ import annotations

import base64

import httpx

from src.core.constants import QWEN_IMAGE_RESULT_HOST_SUFFIXES
from src.domains.image_generation.families import resolve_image_family
from src.domains.image_generation.providers.base import (
    ImageDeliveryError,
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
from src.domains.image_generation.providers.result_download import download_result
from src.domains.image_generation.sizing import ImageSize
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

_PROVIDER = "qwen"
#: How the vendor spells a billed output tier: ``qima_output_1k``, ``qima_output_2k``.
_OUTPUT_TIER_PREFIX = "qima_output_"


class QwenImageClient(ImageGenerationClient):
    """Qwen Image models through the OpenAI-compatible Images endpoint."""

    def __init__(self, *, http_client: httpx.AsyncClient | None = None) -> None:
        """Build the SDK client on the workspace host (``QWEN_BASE_URL``).

        Args:
            http_client: Transport shared by the API call and the result download;
                tests inject a mock transport. Closed by :meth:`aclose`.

        Raises:
            ImageProviderNotConfiguredError: When no Qwen key is configured —
                raised before any transport is opened.
        """
        api_key = require_provider_key(_PROVIDER)
        self._http = http_client or httpx.AsyncClient()
        self._api = openai_sdk_client(_PROVIDER, api_key, http_client=self._http)

    async def generate(self, *, prompt: str, model: str, quality: str, size: str) -> ImageResult:
        """Generate one image (text to image).

        Args:
            prompt: What to draw.
            model: A Qwen Image model.
            quality: The family's one quality; not a vendor parameter.
            size: A size within the family's envelope.

        Returns:
            The downloaded PNG.

        Raises:
            ImageGenerationError: When no usable image comes back.
        """
        return await self._create(action="generate", prompt=prompt, model=model, size=size)

    async def edit(
        self, *, prompt: str, source: SourceImage, model: str, quality: str, size: str
    ) -> ImageResult:
        """Produce one image from a reference image (image to image).

        Args:
            prompt: The modification to make.
            source: The reference image, fitted to the family's input limits.
            model: A Qwen Image model.
            quality: The family's one quality; not a vendor parameter.
            size: The output size, which also sets the tier the reference image
                is billed at.

        Returns:
            The downloaded PNG.

        Raises:
            ImageGenerationError: When no usable image comes back.
        """
        encoded = base64.b64encode(source.data).decode("ascii")
        return await self._create(
            action="edit",
            prompt=prompt,
            model=model,
            size=size,
            image=f"data:{source.mime_type};base64,{encoded}",
        )

    async def aclose(self) -> None:
        """Close the shared HTTP transport."""
        await self._api.close()

    async def _create(
        self, *, action: str, prompt: str, model: str, size: str, image: str | None = None
    ) -> ImageResult:
        # Extension fields travel in ``extra_body``: the SDK merges them at the top
        # level of the JSON body, where the compatible mode reads them. The
        # watermark default is documented false; it is sent anyway, so a vendor
        # default flipping never stamps a person's image.
        extra_body: dict[str, object] = {"watermark": False}
        if image is not None:
            extra_body["image"] = image
        with vendor_errors():
            raw = await self._api.images.with_raw_response.generate(
                model=model, prompt=prompt, n=1, size=size, extra_body=extra_body
            )
        payload = _json_object(raw.http_response)
        url = _result_url(payload)
        _compare_billing_tier(payload.get("usage"), size=size, model=model)
        try:
            png = await download_result(
                url, client=self._http, allowed_host_suffixes=QWEN_IMAGE_RESULT_HOST_SUFFIXES
            )
        except ImageGenerationError as exc:
            # A URL came back: the image exists, and it is billed.
            raise ImageDeliveryError(str(exc)) from exc
        log_provider_call(
            provider=_PROVIDER,
            action=action,
            model=model,
            size=size,
            request_id=raw.request_id,
            result_bytes=len(png),
        )
        return ImageResult(png=png, model=model, provider=_PROVIDER)


def _json_object(response: httpx.Response) -> dict[str, object]:
    """The answer's JSON object.

    Raises:
        ImageGenerationError: When the body is not a JSON object.
    """
    try:
        payload = response.json()
    except ValueError as exc:
        raise ImageGenerationError("Qwen answered with a body that is not JSON") from exc
    if not isinstance(payload, dict):
        raise ImageGenerationError("Qwen answered with a JSON body that is not an object")
    return payload


def _result_url(payload: dict[str, object]) -> str:
    """The first result URL of a compatible-mode answer.

    Raises:
        ImageGenerationError: When the answer carries no URL.
    """
    data = payload.get("data")
    first = data[0] if isinstance(data, list) and data else None
    url = first.get("url") if isinstance(first, dict) else None
    if not isinstance(url, str) or not url:
        raise ImageGenerationError("Qwen returned no image URL")
    return url


def _compare_billing_tier(usage: object, *, size: str, model: str) -> None:
    """Log when the vendor billed another tier than the model family prices."""
    family = resolve_image_family(_PROVIDER, model)
    billed = usage.get("output_image_type") if isinstance(usage, dict) else None
    if family is None or not isinstance(billed, str) or not billed.startswith(_OUTPUT_TIER_PREFIX):
        logger.debug("image_billing_tier_unreported", provider=_PROVIDER, model=model)
        return
    ours = family.tier_of(ImageSize.parse(size))
    vendor = billed.removeprefix(_OUTPUT_TIER_PREFIX)
    if vendor != ours:
        logger.warning(
            "image_billing_tier_mismatch",
            provider=_PROVIDER,
            model=model,
            size=size,
            priced_tier=ours,
            vendor_tier=vendor,
        )
