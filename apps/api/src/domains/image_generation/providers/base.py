"""The contract every image provider client honours (ADR-305).

A client turns one request into ONE PNG image, whatever its vendor's transport:
OpenAI answers with base64, Qwen with a URL the client downloads. The tools, the
cost recorder and the attachment store never see the difference — and neither do
they see a vendor's exceptions: every failure leaves a client as an
:class:`ImageGenerationError` carrying the facts a caller classifies it by (the
HTTP status, the vendor's code, a timeout), never its wording (ADR-303).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import NamedTuple, Self

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ImageGenerationError(Exception):
    """A request that produced no image this application can use.

    Attributes:
        status_code: The vendor's HTTP status, when it answered with one.
        vendor_code: The vendor's own error code (e.g. ``moderation_blocked``).
        timed_out: Whether the vendor did not answer in time.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        vendor_code: str | None = None,
        timed_out: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.vendor_code = vendor_code
        self.timed_out = timed_out


class ImageProviderNotConfiguredError(ImageGenerationError):
    """The provider cannot be called: no key is configured for it."""


class ImageDeliveryError(ImageGenerationError):
    """The vendor produced — and billed — an image this application could not retrieve.

    Distinct from its parent because the cost is real: the caller records it even
    though no image reaches the person (ADR-272 — every euro paid is counted).
    """


class ImageResult(NamedTuple):
    """One generated image.

    Attributes:
        png: The image, PNG-encoded.
        model: The model that produced it (the configured one, which is priced).
        provider: The provider that served it.
        revised_prompt: The vendor's rewrite of the prompt, when it returns one.
    """

    png: bytes
    model: str
    provider: str
    revised_prompt: str | None = None


class SourceImage(NamedTuple):
    """The image an edit starts from, already fitted to its family's limits.

    Attributes:
        data: The encoded image.
        mime_type: ``image/png`` or ``image/jpeg``.
    """

    data: bytes
    mime_type: str


class ImageGenerationClient(ABC):
    """One vendor's image API behind the application's contract.

    A client owns its HTTP transport: use it as an async context manager so the
    transport is closed on the loop that opened it.
    """

    @abstractmethod
    async def generate(self, *, prompt: str, model: str, quality: str, size: str) -> ImageResult:
        """Generate one image from a text prompt.

        Args:
            prompt: What to draw.
            model: The configured image model.
            quality: A quality its family accepts.
            size: A ``WIDTHxHEIGHT`` size its family accepts.

        Returns:
            The generated image.

        Raises:
            ImageGenerationError: When no usable image comes back.
        """

    @abstractmethod
    async def edit(
        self, *, prompt: str, source: SourceImage, model: str, quality: str, size: str
    ) -> ImageResult:
        """Produce one image from a reference image and an instruction.

        Args:
            prompt: The modification to make.
            source: The reference image, fitted to the family's input limits.
            model: The configured image model — the one that runs is the one priced.
            quality: A quality its family accepts.
            size: The output size.

        Returns:
            The edited image.

        Raises:
            ImageGenerationError: When no usable image comes back.
        """

    @abstractmethod
    async def aclose(self) -> None:
        """Close the client's HTTP transport."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()


def log_provider_call(
    *,
    provider: str,
    action: str,
    model: str,
    size: str,
    request_id: str | None,
    result_bytes: int,
) -> None:
    """One line per vendor call that returned an image, with the id support asks for.

    Args:
        provider: The provider that served the call.
        action: ``generate`` or ``edit``.
        model: The model that ran.
        size: The output size.
        request_id: The vendor's request id, when its answer carries one.
        result_bytes: Size of the PNG handed back.
    """
    logger.info(
        "image_provider_call",
        provider=provider,
        action=action,
        model=model,
        size=size,
        request_id=request_id,
        result_bytes=result_bytes,
    )
