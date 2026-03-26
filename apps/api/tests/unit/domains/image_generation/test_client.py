"""Unit tests for image generation client and factory.

Tests the create_image_client factory and OpenAIImageClient (mocked).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.image_generation.client import (
    ImageResult,
    OpenAIImageClient,
    create_image_client,
)


@pytest.mark.unit
class TestCreateImageClient:
    """Tests for create_image_client() factory."""

    def test_openai_returns_client(self) -> None:
        """OpenAI provider returns OpenAIImageClient instance."""
        with patch("src.domains.image_generation.client.LLMConfigOverrideCache") as mock_cache:
            mock_cache.get_api_key.return_value = "sk-test"
            client = create_image_client("openai")
            assert isinstance(client, OpenAIImageClient)

    def test_unknown_provider_raises(self) -> None:
        """Unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="not supported"):
            create_image_client("unknown_provider")


@pytest.mark.unit
class TestOpenAIImageClient:
    """Tests for OpenAIImageClient.generate() (mocked API)."""

    def test_no_api_key_raises(self) -> None:
        """Missing API key raises ValueError."""
        with patch("src.domains.image_generation.client.LLMConfigOverrideCache") as mock_cache:
            mock_cache.get_api_key.return_value = None
            with pytest.raises(ValueError, match="API key not configured"):
                OpenAIImageClient()

    async def test_generate_returns_image_results(self) -> None:
        """Successful generation returns list of ImageResult."""
        mock_img = MagicMock()
        mock_img.b64_json = "base64data=="
        mock_img.revised_prompt = "a revised prompt"

        mock_response = MagicMock()
        mock_response.data = [mock_img]

        with patch("src.domains.image_generation.client.LLMConfigOverrideCache") as mock_cache:
            mock_cache.get_api_key.return_value = "sk-test"
            client = OpenAIImageClient()
            client._client = MagicMock()
            client._client.images.generate = AsyncMock(return_value=mock_response)

            results = await client.generate(
                prompt="a cat",
                model="gpt-image-1",
                quality="low",
                size="1024x1024",
            )

        assert len(results) == 1
        assert isinstance(results[0], ImageResult)
        assert results[0].b64_data == "base64data=="
        assert results[0].model == "gpt-image-1"
        assert results[0].provider == "openai"
        assert results[0].revised_prompt == "a revised prompt"

    async def test_generate_api_error_propagates(self) -> None:
        """API errors propagate to caller."""
        with patch("src.domains.image_generation.client.LLMConfigOverrideCache") as mock_cache:
            mock_cache.get_api_key.return_value = "sk-test"
            client = OpenAIImageClient()
            client._client = MagicMock()
            client._client.images.generate = AsyncMock(side_effect=Exception("API error"))

            with pytest.raises(Exception, match="API error"):
                await client.generate(
                    prompt="a cat",
                    model="gpt-image-1",
                    quality="low",
                    size="1024x1024",
                )
