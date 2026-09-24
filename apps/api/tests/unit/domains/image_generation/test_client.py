"""Unit tests for the image provider registry (ADR-305)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.domains.image_generation.client import (
    assert_image_clients_complete,
    create_image_client,
)
from src.domains.image_generation.families import ALL_FAMILIES, OPENAI_GPT_IMAGE
from src.domains.image_generation.providers.base import ImageProviderNotConfiguredError
from src.domains.image_generation.providers.openai_images import OpenAIImageClient
from src.domains.image_generation.providers.qwen_images import QwenImageClient

_KEY = "src.domains.image_generation.providers.openai_sdk._require_api_key"


@pytest.mark.unit
class TestCreateImageClient:
    """The factory builds the client of the configured provider."""

    @pytest.mark.parametrize(
        ("provider", "client_class"),
        [("openai", OpenAIImageClient), ("qwen", QwenImageClient)],
    )
    async def test_each_family_provider_has_its_client(
        self, provider: str, client_class: type
    ) -> None:
        with patch(_KEY, return_value="sk-test"):
            client = create_image_client(provider)
        try:
            assert isinstance(client, client_class)
        finally:
            await client.aclose()

    def test_unknown_provider_is_refused(self) -> None:
        with pytest.raises(ValueError, match="not supported"):
            create_image_client("gemini")

    @pytest.mark.parametrize("provider", ["openai", "qwen"])
    def test_a_missing_key_fails_clearly(self, provider: str) -> None:
        with patch(_KEY, return_value="NOT_CONFIGURED"):
            with pytest.raises(ImageProviderNotConfiguredError, match="API key not configured"):
                create_image_client(provider)


@pytest.mark.unit
class TestRegistryCompleteness:
    """A family without a client, or a client without a family, stops the import."""

    def test_the_shipped_registry_is_complete(self) -> None:
        assert_image_clients_complete()

    def test_a_family_without_its_client_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match=r"families without a client=\['qwen'\]"):
            assert_image_clients_complete({"openai": OpenAIImageClient}, ALL_FAMILIES)

    def test_a_client_without_a_family_is_refused(self) -> None:
        with pytest.raises(RuntimeError, match=r"clients without a family=\['qwen'\]"):
            assert_image_clients_complete(
                {"openai": OpenAIImageClient, "qwen": QwenImageClient}, (OPENAI_GPT_IMAGE,)
            )
