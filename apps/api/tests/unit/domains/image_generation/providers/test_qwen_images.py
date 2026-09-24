"""Unit tests for the Qwen Image 3.0 client, asserted on the wire (ADR-305).

The SDK runs for real over a mock transport, so what is asserted is the JSON the
vendor would receive — extension fields included — and the download that follows.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from unittest.mock import patch

import httpx
import pytest
from structlog.testing import capture_logs

from src.core.config import settings
from src.domains.image_generation.providers.base import (
    PNG_SIGNATURE,
    ImageDeliveryError,
    ImageGenerationError,
    SourceImage,
)
from src.domains.image_generation.providers.qwen_images import QwenImageClient
from src.domains.image_generation.providers.result_download import download_result

_BASE_URL = "https://workspace.eu-central-1.maas.aliyuncs.com/compatible-mode/v1"
_RESULT_URL = "https://dashscope-result-fra.oss-eu-central-1.aliyuncs.com/out.png?Expires=1"
_PNG = PNG_SIGNATURE + b"pixels"


def _answer(*, tier: str = "qima_output_1k", url: str = _RESULT_URL) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "created": 1,
            "data": [{"url": url}],
            "usage": {
                "output_width": 1024,
                "output_height": 1536,
                "input_image_count": 0,
                "input_image_type": tier.replace("output", "input"),
                "output_image_count": 1,
                "output_image_type": tier,
            },
        },
        headers={"x-request-id": "req-qwen-1"},
    )


class _Vendor:
    """A mock transport playing the compatible endpoint and the result host."""

    def __init__(self, answer: httpx.Response, download: httpx.Response) -> None:
        self.answer = answer
        self.download = download
        self.bodies: list[dict[str, object]] = []
        self.download_headers: list[httpx.Headers] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/generations"):
            self.bodies.append(json.loads(request.content))
            assert request.headers["authorization"] == "Bearer sk-qwen"
            return self.answer
        self.download_headers.append(request.headers)
        return self.download


@pytest.fixture
def vendor_client() -> Callable[[_Vendor], QwenImageClient]:
    def build(vendor: _Vendor) -> QwenImageClient:
        with (
            patch(
                "src.domains.image_generation.providers.openai_sdk._require_api_key",
                return_value="sk-qwen",
            ),
            patch(
                "src.domains.image_generation.providers.openai_sdk._get_base_url",
                return_value=_BASE_URL,
            ),
        ):
            return QwenImageClient(
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(vendor))
            )

    return build


@pytest.mark.unit
class TestGenerate:
    """Text to image: the documented body, then the result downloaded at once."""

    async def test_sends_the_documented_body_and_returns_the_downloaded_png(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        vendor = _Vendor(_answer(), httpx.Response(200, content=_PNG))
        client = vendor_client(vendor)
        try:
            result = await client.generate(
                prompt="a lighthouse",
                model="qwen-image-3.0-pro",
                quality="standard",
                size="1024x1536",
            )
        finally:
            await client.aclose()

        assert vendor.bodies == [
            {
                "model": "qwen-image-3.0-pro",
                "prompt": "a lighthouse",
                "n": 1,
                "size": "1024x1536",
                "watermark": False,
            }
        ]
        assert result.png == _PNG
        assert (result.model, result.provider) == ("qwen-image-3.0-pro", "qwen")
        # The transport is shared: the vendor's key must never reach the result host.
        assert len(vendor.download_headers) == 1
        assert "authorization" not in vendor.download_headers[0]

    async def test_an_answer_without_url_is_an_error(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        vendor = _Vendor(httpx.Response(200, json={"data": []}), httpx.Response(200, content=_PNG))
        client = vendor_client(vendor)
        try:
            with pytest.raises(ImageGenerationError, match="no image URL"):
                await client.generate(
                    prompt="x", model="qwen-image-3.0", quality="standard", size="1024x1024"
                )
        finally:
            await client.aclose()

    async def test_a_vendor_refusal_carries_its_status_and_code(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        """The SDK's refusal leaves the client as the contract's error, on the wire."""
        refusal = httpx.Response(
            400,
            json={"error": {"code": "InvalidParameter", "message": "size", "type": "invalid"}},
        )
        vendor = _Vendor(refusal, httpx.Response(200, content=_PNG))
        client = vendor_client(vendor)
        try:
            with pytest.raises(ImageGenerationError) as raised:
                await client.generate(
                    prompt="x", model="qwen-image-3.0", quality="standard", size="100x100"
                )
        finally:
            await client.aclose()

        assert not isinstance(raised.value, ImageDeliveryError)
        assert (raised.value.status_code, raised.value.vendor_code) == (400, "InvalidParameter")
        assert vendor.download_headers == []

    async def test_a_body_that_is_not_json_is_an_error_not_a_crash(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        vendor = _Vendor(httpx.Response(200, content=b"<html>gateway</html>"), httpx.Response(200))
        client = vendor_client(vendor)
        try:
            with pytest.raises(ImageGenerationError, match="not JSON"):
                await client.generate(
                    prompt="x", model="qwen-image-3.0", quality="standard", size="1024x1024"
                )
        finally:
            await client.aclose()

    async def test_a_url_that_cannot_be_fetched_is_a_billed_delivery_failure(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        """The vendor produced the image, so the failure says it was billed."""
        vendor = _Vendor(_answer(), httpx.Response(503))
        client = vendor_client(vendor)
        try:
            with pytest.raises(ImageDeliveryError, match="HTTP 503"):
                await client.generate(
                    prompt="x", model="qwen-image-3.0", quality="standard", size="1024x1024"
                )
        finally:
            await client.aclose()

    async def test_a_tier_the_vendor_billed_differently_is_logged(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        vendor = _Vendor(_answer(tier="qima_output_2k"), httpx.Response(200, content=_PNG))
        client = vendor_client(vendor)
        try:
            with capture_logs() as logs:
                await client.generate(
                    prompt="x", model="qwen-image-3.0", quality="standard", size="1024x1024"
                )
        finally:
            await client.aclose()

        mismatches = [e for e in logs if e["event"] == "image_billing_tier_mismatch"]
        assert mismatches and mismatches[0]["priced_tier"] == "1k"
        assert mismatches[0]["vendor_tier"] == "2k"


@pytest.mark.unit
class TestEdit:
    """Image to image: the reference image travels as a data URI."""

    async def test_sends_the_source_as_a_data_uri(
        self, vendor_client: Callable[[_Vendor], QwenImageClient]
    ) -> None:
        vendor = _Vendor(_answer(), httpx.Response(200, content=_PNG))
        client = vendor_client(vendor)
        source = SourceImage(data=b"\xff\xd8jpeg", mime_type="image/jpeg")
        try:
            await client.edit(
                prompt="make it night",
                source=source,
                model="qwen-image-3.0",
                quality="standard",
                size="1536x1024",
            )
        finally:
            await client.aclose()

        body = vendor.bodies[0]
        assert (
            body["image"] == "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8jpeg").decode()
        )
        assert (body["model"], body["size"], body["watermark"]) == (
            "qwen-image-3.0",
            "1536x1024",
            False,
        )


@pytest.mark.unit
class TestDownloadResult:
    """The result URL is held to the vendor: host, scheme, redirect, size, format."""

    @staticmethod
    async def _download(url: str, response: httpx.Response) -> bytes:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: response)
        ) as client:
            return await download_result(
                url, client=client, allowed_host_suffixes=(".aliyuncs.com",)
            )

    async def test_downloads_a_png_from_the_vendor_host(self) -> None:
        assert await self._download(_RESULT_URL, httpx.Response(200, content=_PNG)) == _PNG

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/out.png",
            "https://aliyuncs.com.evil.example/out.png",
            "http://dashscope-result.oss-eu-central-1.aliyuncs.com/out.png",
            "file:///etc/passwd",
        ],
    )
    async def test_refuses_anything_but_the_vendor_over_https(self, url: str) -> None:
        with pytest.raises(ImageGenerationError, match="refused"):
            await self._download(url, httpx.Response(200, content=_PNG))

    async def test_a_redirect_is_a_refusal_not_a_hop(self) -> None:
        redirect = httpx.Response(302, headers={"location": "http://169.254.169.254/"})
        with pytest.raises(ImageGenerationError, match="HTTP 302"):
            await self._download(_RESULT_URL, redirect)

    async def test_an_oversized_body_is_abandoned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "image_generation_result_max_mb", 1)
        huge = PNG_SIGNATURE + b"x" * (2 * 1024 * 1024)
        with pytest.raises(ImageGenerationError, match="exceeds"):
            await self._download(_RESULT_URL, httpx.Response(200, content=huge))

    async def test_a_body_that_is_not_a_png_is_refused(self) -> None:
        with pytest.raises(ImageGenerationError, match="not a PNG"):
            await self._download(_RESULT_URL, httpx.Response(200, content=b"<html>error</html>"))
