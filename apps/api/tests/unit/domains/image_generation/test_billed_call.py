"""One billed call to the image model: what the vendor billed is recorded, and only that.

The image tools and a document's illustrations share this door (ADR-305,
ADR-272): an image delivered is billed, an image produced and lost on the way
(``ImageDeliveryError``) is billed too, a refusal or a timeout is not — and a
failure always reaches the caller typed.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

import pytest

from src.domains.image_generation import billed_call
from src.domains.image_generation.families import OPENAI_GPT_IMAGE
from src.domains.image_generation.options_cache import ModelOptions
from src.domains.image_generation.providers.base import (
    ImageDeliveryError,
    ImageGenerationClient,
    ImageGenerationError,
    ImageResult,
    SourceImage,
)

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\nfake"


def _result() -> ImageResult:
    return ImageResult(png=_PNG, model="image-model", provider="vendor")


def _options() -> ModelOptions:
    return ModelOptions(
        model="image-model", provider="vendor", family=OPENAI_GPT_IMAGE, qualities=(), sizes=()
    )


class _Client(ImageGenerationClient):
    """A vendor client that answers, or fails, as told — and says when it was closed."""

    def __init__(self, outcome: ImageResult | Exception) -> None:
        self.outcome = outcome
        self.prompts: list[str] = []
        self.closed = False

    async def generate(self, *, prompt: str, model: str, quality: str, size: str) -> ImageResult:
        self.prompts.append(prompt)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    async def edit(
        self, *, prompt: str, source: SourceImage, model: str, quality: str, size: str
    ) -> ImageResult:
        raise NotImplementedError

    async def aclose(self) -> None:
        self.closed = True


def _serving(client: _Client) -> Callable[[str], ImageGenerationClient]:
    def factory(provider: str) -> ImageGenerationClient:
        assert provider == "vendor"
        return client

    return factory


async def _call(client: _Client, bills: list[float]) -> ImageResult:
    with patch.object(billed_call, "create_image_client", _serving(client)):
        return await billed_call.call_billed(
            _options(),
            lambda vendor: vendor.generate(
                prompt="p", model="image-model", quality="low", size="1024x1024"
            ),
            bill=bills.append,
        )


class TestTheBill:
    async def test_a_delivered_image_is_billed_once_and_the_client_closed(self) -> None:
        bills: list[float] = []
        client = _Client(_result())

        result = await _call(client, bills)

        assert result.png == _PNG
        assert len(bills) == 1 and bills[0] >= 0.0
        assert client.closed

    async def test_an_image_lost_on_the_way_is_billed_and_still_fails(self) -> None:
        bills: list[float] = []
        client = _Client(ImageDeliveryError("download failed"))

        with pytest.raises(ImageDeliveryError):
            await _call(client, bills)

        assert len(bills) == 1
        assert client.closed

    @pytest.mark.parametrize(
        "error",
        [
            ImageGenerationError("refused", status_code=400, vendor_code="moderation_blocked"),
            ImageGenerationError("throttled", status_code=429),
            ImageGenerationError("slow", timed_out=True),
        ],
    )
    async def test_a_call_the_vendor_did_not_bill_is_not_billed(
        self, error: ImageGenerationError
    ) -> None:
        bills: list[float] = []

        with pytest.raises(ImageGenerationError) as raised:
            await _call(_Client(error), bills)

        assert raised.value is error
        assert bills == []


class TestGenerateBilled:
    async def test_one_generation_is_billed_as_one_image_of_its_size_and_quality(self) -> None:
        client = _Client(_result())

        with (
            patch.object(billed_call, "create_image_client", _serving(client)),
            patch.object(billed_call, "track_image_generation_call") as tracked,
        ):
            result = await billed_call.generate_billed(
                _options(), prompt="a lighthouse", quality="medium", size="1024x1536"
            )

        assert result.png == _PNG
        assert client.prompts == ["a lighthouse"]
        kwargs = tracked.call_args.kwargs
        assert (kwargs["model"], kwargs["quality"], kwargs["size"]) == (
            "image-model",
            "medium",
            "1024x1536",
        )
        assert kwargs["image_count"] == 1 and kwargs["prompt"] == "a lighthouse"
