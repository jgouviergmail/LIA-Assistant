"""Image provider registry: which client serves which provider (ADR-305).

A family (``families.py``) says what a model accepts; a client (``providers/``)
says how its vendor is reached. This module joins them and refuses to import when
they disagree: a family whose provider has no client would be a model offered
nowhere, in silence, and a client serving no family is dead code (ADR-085). The
boot runs the same check (``run_failfast_validations``). So a model a family
declares is servable, and ``resolve_image_family`` is the one question every
surface asks.

To add a vendor: declare its family in ``families.py``, write its client under
``providers/``, register the client here, then price its models in
``image_generation_pricing`` (seed + migration).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from src.domains.image_generation.families import ALL_FAMILIES, ImageFamily
from src.domains.image_generation.providers.base import ImageGenerationClient
from src.domains.image_generation.providers.openai_images import OpenAIImageClient
from src.domains.image_generation.providers.qwen_images import QwenImageClient

_IMAGE_CLIENT_REGISTRY: dict[str, type[ImageGenerationClient]] = {
    "openai": OpenAIImageClient,
    "qwen": QwenImageClient,
}


def create_image_client(provider: str) -> ImageGenerationClient:
    """Build the client that serves ``provider``.

    Args:
        provider: The configured model's provider.

    Returns:
        A client; use it as an async context manager.

    Raises:
        ValueError: When no client serves the provider.
        ImageProviderNotConfiguredError: When the provider's key is missing.
    """
    client_class = _IMAGE_CLIENT_REGISTRY.get(provider)
    if client_class is None:
        raise ValueError(
            f"Image generation provider '{provider}' not supported. "
            f"Available: {sorted(_IMAGE_CLIENT_REGISTRY)}"
        )
    return client_class()


def assert_image_clients_complete(
    registry: Mapping[str, type[ImageGenerationClient]] = _IMAGE_CLIENT_REGISTRY,
    families: Iterable[ImageFamily] = ALL_FAMILIES,
) -> None:
    """Refuse a family without a client, and a client without a family.

    Args:
        registry: Provider → client class.
        families: The declared families.

    Raises:
        RuntimeError: Naming each provider on one side only.
    """
    family_providers = {family.provider for family in families}
    unserved = sorted(family_providers - set(registry))
    unused = sorted(set(registry) - family_providers)
    if unserved or unused:
        raise RuntimeError(
            "Image families and clients disagree: "
            f"families without a client={unserved}, clients without a family={unused}"
        )


assert_image_clients_complete()
