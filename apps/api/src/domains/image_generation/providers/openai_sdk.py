"""The OpenAI SDK as the transport of the OpenAI-compatible image vendors (ADR-305).

OpenAI's Images API and Qwen's compatible mode speak one wire, so both clients
reach their vendor through an SDK client built here, in one way: the key and the
base URL resolve exactly as the chat factory's do (``_require_api_key``,
``_get_base_url``, so ``{PROVIDER}_BASE_URL`` reaches an image call too) and the
timeout is the image step's ceiling. The SDK's failures are translated into the
client contract (:func:`vendor_errors`), so no tool ever reads an SDK exception.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from src.core.config import settings
from src.domains.image_generation.providers.base import (
    ImageGenerationError,
    ImageProviderNotConfiguredError,
)
from src.infrastructure.llm.providers.adapter import (
    API_KEY_NOT_CONFIGURED,
    _get_base_url,
    _require_api_key,
)


def require_provider_key(provider: str) -> str:
    """The provider's API key, resolved as the chat factory resolves it.

    Args:
        provider: The provider identifier.

    Returns:
        The key (Admin UI first, then the environment).

    Raises:
        ImageProviderNotConfiguredError: When neither holds a key — a clear
            failure beats a 401.
    """
    key = _require_api_key(provider)
    if key == API_KEY_NOT_CONFIGURED:
        raise ImageProviderNotConfiguredError(
            f"{provider} API key not configured. "
            "Set it via Settings > Administration > LLM Configuration."
        )
    return key


def openai_sdk_client(
    provider: str, api_key: str, *, http_client: httpx.AsyncClient | None = None
) -> AsyncOpenAI:
    """An SDK client on the provider's base URL, bounded by the image step's ceiling.

    Args:
        provider: The provider identifier (its base URL is resolved from it).
        api_key: The key :func:`require_provider_key` returned — resolved BEFORE
            the caller builds a transport, so a missing key leaves none open.
        http_client: A transport the caller also uses; the SDK closes it.

    Returns:
        The SDK client; ``close()`` it on the loop that opened it.
    """
    return AsyncOpenAI(
        api_key=api_key,
        base_url=_get_base_url(provider),
        timeout=settings.max_image_generation_tool_timeout_seconds,
        http_client=http_client,
    )


@contextmanager
def vendor_errors() -> Iterator[None]:
    """Translate the SDK's failures into the client contract.

    The facts a caller classifies a failure by — the status, the vendor's code, a
    timeout — travel as attributes; the message keeps the vendor's own wording
    for the model, never for a log.

    Raises:
        ImageGenerationError: For a vendor refusal, a timeout or an unreachable
            vendor.
    """
    try:
        yield
    except APIStatusError as exc:
        # The SDK copies ``code`` from the body as it came: a compatible vendor
        # may spell it as a number.
        vendor_code = exc.code if isinstance(exc.code, str) else None
        raise ImageGenerationError(
            str(exc), status_code=exc.status_code, vendor_code=vendor_code
        ) from exc
    except APITimeoutError as exc:
        raise ImageGenerationError("The vendor did not answer in time", timed_out=True) from exc
    except APIConnectionError as exc:
        raise ImageGenerationError("The vendor could not be reached") from exc
