"""Image generation client with multi-provider support.

Architecture:
- ImageGenerationClient: Abstract base class defining the generation contract.
- OpenAIImageClient: OpenAI implementation (generate via Images API, edit via Responses API).
- create_image_client(): Factory function (follows ProviderAdapter pattern).

Extensibility:
    To add a new provider (e.g., Gemini):
    1. Create GeminiImageClient(ImageGenerationClient) with generate()/edit() impl
    2. Add "gemini": GeminiImageClient to _IMAGE_CLIENT_REGISTRY
    3. Add pricing rows in image_generation_pricing table
    4. Admin selects provider via LLM Config UI

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NamedTuple

from openai import AsyncOpenAI

from src.domains.llm_config.cache import LLMConfigOverrideCache
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# Provider-agnostic result
# ============================================================================


class ImageResult(NamedTuple):
    """Provider-agnostic result from image generation.

    Attributes:
        b64_data: Base64-encoded image data.
        revised_prompt: Provider-revised prompt (if available).
        model: Model that generated the image.
        provider: Provider identifier (e.g., "openai").
        response_id: Provider response ID for follow-up edits (OpenAI Responses API).
    """

    b64_data: str
    revised_prompt: str | None
    model: str
    provider: str
    response_id: str | None = None


# ============================================================================
# Abstract client (extensible to any provider)
# ============================================================================


class ImageGenerationClient(ABC):
    """Abstract base class for image generation providers.

    Extend this class to add new providers (Gemini, Stability AI, etc.).
    Each provider implements generate() and edit(), returning standardized ImageResult.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        quality: str,
        size: str,
        n: int = 1,
    ) -> list[ImageResult]:
        """Generate image(s) from a text prompt.

        Args:
            prompt: Text description of the image to generate.
            model: Provider-specific model name (e.g., "gpt-image-1").
            quality: Quality level (provider-specific values).
            size: Image dimensions (provider-specific values).
            n: Number of images to generate.

        Returns:
            List of ImageResult with base64 data.

        Raises:
            Exception: On API failure (provider-specific).
        """

    @abstractmethod
    async def edit(
        self,
        prompt: str,
        source_image_b64: str,
        model: str,
        quality: str,
        size: str,
    ) -> list[ImageResult]:
        """Edit an existing image based on a text prompt.

        Uses the provider's image editing capability (e.g., OpenAI Responses API
        "Generate vs Edit" mode — NOT mask-based editing).

        Args:
            prompt: Text description of the desired modification.
            source_image_b64: Base64-encoded source image (PNG).
            model: Provider-specific model name.
            quality: Quality level.
            size: Target image dimensions.

        Returns:
            List of ImageResult with base64 data of the edited image.

        Raises:
            Exception: On API failure (provider-specific).
        """


# ============================================================================
# OpenAI implementation (gpt-image-1, gpt-image-1.5, gpt-image-1-mini)
# ============================================================================


class OpenAIImageClient(ImageGenerationClient):
    """OpenAI image client.

    - generate(): Uses Images API (images.generate) for new image creation.
    - edit(): Uses Responses API (responses.create) with image_generation tool
      for editing an existing image ("Generate vs Edit" approach, no masks).

    API key resolved from LLMConfigOverrideCache (admin UI) with graceful fallback.
    """

    def __init__(self) -> None:
        """Initialize OpenAI client with API key from admin config.

        Raises:
            ValueError: If OpenAI API key is not configured.
        """
        api_key = LLMConfigOverrideCache.get_api_key("openai")
        if not api_key:
            raise ValueError(
                "OpenAI API key not configured. "
                "Set it via Settings > Administration > LLM Configuration."
            )
        self._client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        model: str = "gpt-image-1",
        quality: str = "medium",
        size: str = "1024x1024",
        n: int = 1,
    ) -> list[ImageResult]:
        """Generate image(s) using OpenAI Images API.

        Args:
            prompt: Text description of the image to generate.
            model: OpenAI model name (e.g., "gpt-image-1").
            quality: Quality level ("low", "medium", "high").
            size: Image dimensions ("1024x1024", "1536x1024", "1024x1536").
            n: Number of images to generate (1-4).

        Returns:
            List of ImageResult with base64 PNG data.

        Raises:
            openai.APIError: On OpenAI API failure.
            openai.RateLimitError: On rate limit exceeded.
        """
        logger.info(
            "image_generation_request",
            model=model,
            quality=quality,
            size=size,
            n=n,
            prompt_length=len(prompt),
        )

        # gpt-image-1+: uses output_format (not response_format which was DALL-E era)
        response = await self._client.images.generate(  # type: ignore[call-overload]
            model=model,
            prompt=prompt,
            n=n,
            size=size,
            quality=quality,
            output_format="png",
        )

        results = [
            ImageResult(
                b64_data=img.b64_json or "",
                revised_prompt=getattr(img, "revised_prompt", None),
                model=model,
                provider="openai",
            )
            for img in response.data
        ]

        logger.info(
            "image_generation_success",
            model=model,
            quality=quality,
            size=size,
            images_count=len(results),
        )

        return results

    async def edit(
        self,
        prompt: str,
        source_image_b64: str,
        model: str = "gpt-4.1-mini",
        quality: str = "medium",
        size: str = "1024x1024",
    ) -> list[ImageResult]:
        """Edit an image using OpenAI Responses API with image_generation tool.

        Uses the "Generate vs Edit" approach: passes the source image as an
        input_image content part alongside the edit instruction. The Responses
        API uses a TEXT model that orchestrates the image_generation tool.

        This is NOT mask-based editing (images.edit endpoint). It uses the
        Responses API (responses.create) with tools=[{"type": "image_generation"}].

        Args:
            prompt: Text description of the desired modification.
            source_image_b64: Base64-encoded source image (PNG/JPEG).
            model: TEXT model for the Responses API (e.g., "gpt-4.1-mini").
                NOT an image model — the image model is implicit in the tool.
            quality: Quality level ("low", "medium", "high").
            size: Target image dimensions.

        Returns:
            List of ImageResult with base64 data of the edited image.

        Raises:
            openai.APIError: On OpenAI API failure.
        """
        logger.info(
            "image_edit_request",
            model=model,
            quality=quality,
            size=size,
            prompt_length=len(prompt),
            source_image_size_kb=len(source_image_b64) * 3 // 4 // 1024,
        )

        data_url = f"data:image/png;base64,{source_image_b64}"

        # OpenAI Responses API with image_generation tool — dict-based input
        # requires type: ignore because TypedDict stubs don't match runtime dicts
        input_messages: list[dict] = [  # noqa: UP006
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": data_url,
                    },
                    {
                        "type": "input_text",
                        "text": prompt,
                    },
                ],
            },
        ]
        tool_config: list[dict] = [  # noqa: UP006
            {
                "type": "image_generation",
                "quality": quality,
                "size": size,
            },
        ]
        response = await self._client.responses.create(
            model=model,
            input=input_messages,  # type: ignore[arg-type]
            tools=tool_config,  # type: ignore[arg-type]
        )

        # Extract generated images from response output
        results: list[ImageResult] = []
        for output in response.output:
            if output.type == "image_generation_call":
                results.append(
                    ImageResult(
                        b64_data=output.result or "",
                        revised_prompt=None,
                        model=model,
                        provider="openai",
                        response_id=response.id,
                    )
                )

        logger.info(
            "image_edit_success",
            model=model,
            quality=quality,
            size=size,
            images_count=len(results),
            response_id=response.id,
        )

        return results


# ============================================================================
# Factory (centralized, extensible, follows ProviderAdapter pattern)
# ============================================================================

# Provider → Client class mapping.
# To add a new provider: create XxxImageClient, add entry here.
_IMAGE_CLIENT_REGISTRY: dict[str, type[ImageGenerationClient]] = {
    "openai": OpenAIImageClient,
}


def create_image_client(provider: str) -> ImageGenerationClient:
    """Factory function to create the right image generation client.

    Follows the same pattern as ProviderAdapter.create_llm() in
    src/infrastructure/llm/providers/adapter.py.

    Args:
        provider: Provider name from LLM config (e.g., "openai").

    Returns:
        Configured ImageGenerationClient instance.

    Raises:
        ValueError: If provider not supported for image generation.
    """
    client_class = _IMAGE_CLIENT_REGISTRY.get(provider)
    if client_class is None:
        raise ValueError(
            f"Image generation provider '{provider}' not supported. "
            f"Available: {list(_IMAGE_CLIENT_REGISTRY.keys())}"
        )
    return client_class()
