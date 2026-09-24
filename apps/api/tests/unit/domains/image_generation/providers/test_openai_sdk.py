"""Unit tests for the SDK seam both OpenAI-compatible image clients share (ADR-305)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import openai
import pytest

from src.domains.image_generation.providers.base import (
    ImageGenerationError,
    ImageProviderNotConfiguredError,
)
from src.domains.image_generation.providers.openai_sdk import (
    require_provider_key,
    vendor_errors,
)

_REQUEST = httpx.Request("POST", "https://vendor.example/v1/images/generations")


def _status_error(status: int, body: object) -> openai.APIStatusError:
    return openai.APIStatusError(
        f"Error code: {status}", response=httpx.Response(status, request=_REQUEST), body=body
    )


@pytest.mark.unit
class TestVendorErrors:
    """What a caller classifies a failure by travels as attributes, never as words."""

    def test_a_refusal_carries_the_status_and_the_vendor_code(self) -> None:
        with pytest.raises(ImageGenerationError) as raised:
            with vendor_errors():
                raise _status_error(400, {"code": "moderation_blocked", "message": "no"})
        assert (raised.value.status_code, raised.value.vendor_code) == (400, "moderation_blocked")
        assert not raised.value.timed_out

    def test_a_numeric_vendor_code_is_not_passed_off_as_one(self) -> None:
        with pytest.raises(ImageGenerationError) as raised:
            with vendor_errors():
                raise _status_error(429, {"code": 1302})
        assert (raised.value.status_code, raised.value.vendor_code) == (429, None)

    def test_a_timeout_says_so(self) -> None:
        with pytest.raises(ImageGenerationError) as raised:
            with vendor_errors():
                raise openai.APITimeoutError(request=_REQUEST)
        assert raised.value.timed_out and raised.value.status_code is None

    def test_an_unreachable_vendor_has_no_status(self) -> None:
        with pytest.raises(ImageGenerationError, match="could not be reached") as raised:
            with vendor_errors():
                raise openai.APIConnectionError(request=_REQUEST)
        assert raised.value.status_code is None and not raised.value.timed_out

    def test_anything_else_is_not_disguised_as_a_vendor_failure(self) -> None:
        with pytest.raises(KeyError):
            with vendor_errors():
                raise KeyError("a defect of ours")


@pytest.mark.unit
class TestRequireProviderKey:
    """A missing key is its own failure, raised before any call."""

    def test_returns_the_configured_key(self) -> None:
        with patch(
            "src.domains.image_generation.providers.openai_sdk._require_api_key",
            return_value="sk-live",
        ):
            assert require_provider_key("qwen") == "sk-live"

    def test_a_missing_key_is_not_configured(self) -> None:
        with patch(
            "src.domains.image_generation.providers.openai_sdk._require_api_key",
            return_value="NOT_CONFIGURED",
        ):
            with pytest.raises(ImageProviderNotConfiguredError, match="qwen API key"):
                require_provider_key("qwen")
