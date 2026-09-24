"""Unit tests for the OpenAI GPT Image client (ADR-305)."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.image_generation.families import OPENAI_GPT_IMAGE
from src.domains.image_generation.providers import openai_images
from src.domains.image_generation.providers.base import (
    PNG_SIGNATURE,
    ImageGenerationError,
    SourceImage,
)
from src.domains.image_generation.providers.openai_images import OpenAIImageClient

_PNG = PNG_SIGNATURE + b"pixels"


def _answer(*, b64: str | None, revised: str | None = None) -> SimpleNamespace:
    image = SimpleNamespace(b64_json=b64, revised_prompt=revised)
    return SimpleNamespace(data=[image], _request_id="req_123")


@pytest.fixture
async def client() -> AsyncIterator[OpenAIImageClient]:
    with patch(
        "src.domains.image_generation.providers.openai_sdk._require_api_key",
        return_value="sk-test",
    ):
        built = OpenAIImageClient()
    yield built
    await built.aclose()


@pytest.mark.unit
class TestGenerate:
    """``images.generate`` on the configured model."""

    async def test_sends_the_configured_model_and_decodes_the_png(
        self, client: OpenAIImageClient
    ) -> None:
        generate = AsyncMock(
            return_value=_answer(b64=base64.b64encode(_PNG).decode(), revised="a cat")
        )
        with patch.object(client._client.images, "generate", generate):
            result = await client.generate(
                prompt="a cat", model="gpt-image-2", quality="low", size="1024x1536"
            )

        assert generate.await_args is not None
        assert generate.await_args.kwargs == {
            "model": "gpt-image-2",
            "prompt": "a cat",
            "n": 1,
            "size": "1024x1536",
            "quality": "low",
            "output_format": "png",
        }
        assert result.png == _PNG
        assert (result.model, result.provider, result.revised_prompt) == (
            "gpt-image-2",
            "openai",
            "a cat",
        )

    async def test_an_answer_without_image_is_an_error(self, client: OpenAIImageClient) -> None:
        with patch.object(
            client._client.images, "generate", AsyncMock(return_value=_answer(b64=None))
        ):
            with pytest.raises(ImageGenerationError, match="no image data"):
                await client.generate(
                    prompt="x", model="gpt-image-2", quality="low", size="1024x1024"
                )

    async def test_a_quality_outside_the_family_never_reaches_openai(
        self, client: OpenAIImageClient
    ) -> None:
        generate = AsyncMock()
        with patch.object(client._client.images, "generate", generate):
            with pytest.raises(ImageGenerationError, match="not an OpenAI GPT Image quality"):
                await client.generate(
                    prompt="x", model="gpt-image-2", quality="standard", size="1024x1024"
                )
        generate.assert_not_awaited()


@pytest.mark.unit
class TestEdit:
    """``images.edit`` on the configured model — no text model, no Responses detour."""

    async def test_edits_with_the_configured_image_model(self, client: OpenAIImageClient) -> None:
        edit = AsyncMock(return_value=_answer(b64=base64.b64encode(_PNG).decode()))
        source = SourceImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg")
        with patch.object(client._client.images, "edit", edit):
            result = await client.edit(
                prompt="make it blue",
                source=source,
                model="gpt-image-2",
                quality="medium",
                size="1536x1024",
            )

        assert edit.await_args is not None
        kwargs = edit.await_args.kwargs
        assert kwargs["model"] == "gpt-image-2"
        assert kwargs["image"] == ("source.jpg", b"\xff\xd8jpeg", "image/jpeg")
        assert (kwargs["prompt"], kwargs["quality"], kwargs["size"], kwargs["n"]) == (
            "make it blue",
            "medium",
            "1536x1024",
            1,
        )
        assert result.png == _PNG and result.model == "gpt-image-2"


@pytest.mark.unit
def test_the_quality_table_is_the_family_vocabulary() -> None:
    """The SDK narrowing table and the family declare one vocabulary."""
    assert tuple(openai_images._QUALITIES) == OPENAI_GPT_IMAGE.qualities
