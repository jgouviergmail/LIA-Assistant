"""What the image tools ask the vendor and what they bill (ADR-305).

The caller's database read and the attachment write are replaced at their own
seams; everything between them runs for real: the preference resolution, the
source preparation, the client call and the cost record.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool
from PIL import Image

from src.domains.agents.tools import image_generation_tools
from src.domains.agents.tools.image_generation_tools import _Caller
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from src.domains.image_generation.families import OPENAI_GPT_IMAGE, QWEN_IMAGE_3
from src.domains.image_generation.options_cache import ModelOptions, QualityOption, SizeOption
from src.domains.image_generation.providers.base import (
    PNG_SIGNATURE,
    ImageDeliveryError,
    ImageGenerationError,
    ImageProviderNotConfiguredError,
    ImageResult,
    SourceImage,
)
from tests.helpers.runtime_context import make_tool_runtime

_PNG = PNG_SIGNATURE + b"generated"
_URL = "/api/v1/attachments/00000000-0000-0000-0000-000000000001"


def _qwen_options() -> ModelOptions:
    return ModelOptions(
        model="qwen-image-3.0-pro",
        provider="qwen",
        family=QWEN_IMAGE_3,
        qualities=(QualityOption("standard", Decimal("0.03438"), Decimal("0.068761")),),
        sizes=(
            SizeOption("1024x1024", "square", "1k"),
            SizeOption("1536x1024", "landscape", "1k"),
            SizeOption("1024x1536", "portrait", "1k"),
            SizeOption("2048x2048", "square", "2k"),
            SizeOption("2448x1632", "landscape", "2k"),
            SizeOption("1632x2448", "portrait", "2k"),
        ),
    )


def _openai_options() -> ModelOptions:
    return ModelOptions(
        model="gpt-image-2",
        provider="openai",
        family=OPENAI_GPT_IMAGE,
        qualities=(
            QualityOption("low", Decimal("0.011"), Decimal("0.016")),
            QualityOption("medium", Decimal("0.042"), Decimal("0.063")),
        ),
        sizes=(
            SizeOption("1024x1024", "square", None),
            SizeOption("1536x1024", "landscape", None),
            SizeOption("1024x1536", "portrait", None),
        ),
    )


def _caller(
    options: ModelOptions, *, quality: str, size: str, output_format: str = "png"
) -> _Caller:
    return _Caller(
        user_id=uuid.uuid4(),
        thread_id="thread-1",
        stored_quality=quality,
        stored_size=size,
        options=options,
        output_format=output_format,
    )


class _FakeClient:
    """Records what the tool asked, answers one PNG."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error
        self.closed = False

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        self.closed = True

    async def generate(self, **kwargs: Any) -> ImageResult:
        self.calls.append({"action": "generate", **kwargs})
        if self.error:
            raise self.error
        return ImageResult(png=_PNG, model=kwargs["model"], provider="fake")

    async def edit(self, **kwargs: Any) -> ImageResult:
        self.calls.append({"action": "edit", **kwargs})
        return ImageResult(png=_PNG, model=kwargs["model"], provider="fake")


@pytest.fixture(autouse=True)
def _fresh_rate_limits() -> Iterator[None]:
    _rate_limit_tracker.clear()
    yield
    _rate_limit_tracker.clear()


def _photo(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _patched(caller: _Caller, client: _FakeClient, *, source: bytes | None = None) -> Any:
    patches = [
        patch.object(image_generation_tools, "_resolve_caller", AsyncMock(return_value=caller)),
        patch.object(image_generation_tools, "_save_image", AsyncMock(return_value=_URL)),
        patch("src.domains.image_generation.client.create_image_client", return_value=client),
        patch("src.domains.image_generation.tracker.track_image_generation_call"),
    ]
    if source is not None:
        patches.append(
            patch.object(image_generation_tools, "_resolve_source", AsyncMock(return_value=source))
        )
    return patches


async def _run(tool: StructuredTool, prompt: str) -> UnifiedToolOutput:
    """Call a tool's coroutine the way the runtime does, with a real tool runtime."""
    assert tool.coroutine is not None
    result = await tool.coroutine(prompt=prompt, runtime=make_tool_runtime())
    assert isinstance(result, UnifiedToolOutput)
    return result


@pytest.mark.unit
class TestGenerateImage:
    """The person's intent, mapped onto the configured model, is what runs."""

    async def test_a_stored_openai_quality_runs_as_the_qwen_quality(self) -> None:
        caller = _caller(_qwen_options(), quality="high", size="1536x1024")
        client = _FakeClient()
        patches = _patched(caller, client)
        with patches[0], patches[1] as save, patches[2], patches[3] as track:
            result = await _run(image_generation_tools.generate_image, "a lighthouse")

        assert isinstance(result, UnifiedToolOutput) and result.success
        assert client.calls == [
            {
                "action": "generate",
                "prompt": "a lighthouse",
                "model": "qwen-image-3.0-pro",
                "quality": "standard",
                "size": "1536x1024",
            }
        ]
        assert client.closed
        track.assert_called_once()
        billed = track.call_args.kwargs
        assert (billed["model"], billed["quality"], billed["size"], billed["image_count"]) == (
            "qwen-image-3.0-pro",
            "standard",
            "1536x1024",
            1,
        )
        assert billed.get("input_image_count", 0) == 0
        save.assert_awaited_once()
        assert result.structured_data["image_url"] == _URL

    async def test_a_vendor_refusal_is_returned_and_nothing_is_billed(self) -> None:
        caller = _caller(_openai_options(), quality="low", size="1024x1024")
        client = _FakeClient(error=ImageGenerationError("OpenAI returned no image data"))
        patches = _patched(caller, client)
        with patches[0], patches[1] as save, patches[2], patches[3] as track:
            result = await _run(image_generation_tools.generate_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert "no image data" in result.message
        track.assert_not_called()
        save.assert_not_awaited()

    async def test_an_image_billed_but_not_delivered_is_recorded(self) -> None:
        """The vendor charged for it: the cost is counted even though no card shows."""
        caller = _caller(_qwen_options(), quality="standard", size="1024x1024")
        client = _FakeClient(error=ImageDeliveryError("Result download answered HTTP 503"))
        patches = _patched(caller, client)
        with patches[0], patches[1] as save, patches[2], patches[3] as track:
            result = await _run(image_generation_tools.generate_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert result.error_code == "EXTERNAL_API_ERROR"
        track.assert_called_once()
        billed = track.call_args.kwargs
        assert (billed["model"], billed["size"], billed["image_count"]) == (
            "qwen-image-3.0-pro",
            "1024x1024",
            1,
        )
        save.assert_not_awaited()


@pytest.mark.unit
class TestFailureCodes:
    """A vendor failure reads in the shared taxonomy, so the answer says what to do."""

    @pytest.mark.parametrize(
        ("error", "code"),
        [
            (ImageGenerationError("throttled", status_code=429), "RATE_LIMIT_EXCEEDED"),
            (
                ImageGenerationError("refused", status_code=400, vendor_code="moderation_blocked"),
                "INVALID_INPUT",
            ),
            (ImageGenerationError("bad key", status_code=401), "UNAUTHORIZED"),
            (ImageGenerationError("down", status_code=503), "EXTERNAL_API_ERROR"),
            (ImageGenerationError("slow", timed_out=True), "TIMEOUT"),
            (ImageGenerationError("OpenAI returned no image data"), "EXTERNAL_API_ERROR"),
        ],
    )
    async def test_a_vendor_failure_is_classified_by_its_facts(
        self, error: ImageGenerationError, code: str
    ) -> None:
        caller = _caller(_openai_options(), quality="low", size="1024x1024")
        patches = _patched(caller, _FakeClient(error=error))
        with patches[0], patches[1], patches[2], patches[3] as track:
            result = await _run(image_generation_tools.generate_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert result.error_code == code
        track.assert_not_called()

    async def test_a_provider_without_key_is_a_configuration_error(self) -> None:
        caller = _caller(_qwen_options(), quality="standard", size="1024x1024")
        patches = _patched(caller, _FakeClient())
        missing = ImageProviderNotConfiguredError("qwen API key not configured.")
        with (
            patches[0],
            patches[1],
            patch("src.domains.image_generation.client.create_image_client", side_effect=missing),
            patches[3] as track,
        ):
            result = await _run(image_generation_tools.generate_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert result.error_code == "CONFIGURATION_ERROR"
        assert "qwen API key not configured" in result.message
        track.assert_not_called()

    async def test_a_defect_of_ours_is_internal_and_keeps_its_message_out(self) -> None:
        caller = _caller(_openai_options(), quality="low", size="1024x1024")
        patches = _patched(caller, _FakeClient(error=RuntimeError("secret internal detail")))
        with patches[0], patches[1], patches[2], patches[3] as track:
            result = await _run(image_generation_tools.generate_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert result.error_code == "INTERNAL_ERROR"
        assert "secret internal detail" not in result.message
        track.assert_not_called()


@pytest.mark.unit
class TestEditImage:
    """An edit keeps the source's proportions and bills its reference image."""

    async def test_qwen_edit_follows_the_source_and_counts_the_reference_image(self) -> None:
        caller = _caller(_qwen_options(), quality="standard", size="1632x2448")
        client = _FakeClient()
        patches = _patched(caller, client, source=_photo(4000, 3000))
        with patches[0], patches[1], patches[2], patches[3] as track, patches[4]:
            result = await _run(image_generation_tools.edit_image, "make it night")

        assert isinstance(result, UnifiedToolOutput) and result.success
        call = client.calls[0]
        # A 4:3 landscape photo, preferred tier 2K → the 2K landscape.
        assert (call["action"], call["size"], call["quality"]) == ("edit", "2448x1632", "standard")
        source: SourceImage = call["source"]
        prepared = Image.open(io.BytesIO(source.data))
        # Qwen keeps up to 2048 px of the source: its input ceiling, not the output.
        assert prepared.size == (2048, 1536)
        billed = track.call_args.kwargs
        assert (billed["image_count"], billed["input_image_count"], billed["size"]) == (
            1,
            1,
            "2448x1632",
        )

    async def test_openai_edit_fits_the_source_within_the_output(self) -> None:
        caller = _caller(_openai_options(), quality="medium", size="1024x1536")
        client = _FakeClient()
        patches = _patched(caller, client, source=_photo(3000, 4000))
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            await _run(image_generation_tools.edit_image, "add a hat")

        call = client.calls[0]
        assert (call["model"], call["size"], call["quality"]) == (
            "gpt-image-2",
            "1024x1536",
            "medium",
        )
        prepared = Image.open(io.BytesIO(call["source"].data))
        assert prepared.size[0] <= 1024 and prepared.size[1] <= 1536

    async def test_an_unreadable_source_is_refused_before_any_vendor_call(self) -> None:
        caller = _caller(_qwen_options(), quality="standard", size="1024x1024")
        client = _FakeClient()
        patches = _patched(caller, client, source=b"%PDF-1.7 not an image")
        with patches[0], patches[1], patches[2], patches[3] as track, patches[4]:
            result = await _run(image_generation_tools.edit_image, "x")

        assert isinstance(result, UnifiedToolOutput) and not result.success
        assert "cannot be edited" in result.message
        assert client.calls == []
        track.assert_not_called()


@pytest.mark.unit
class TestTheImageIsStoredInThePersonSFormat:
    """The Format preference is applied: converted once, whatever the vendor."""

    @pytest.mark.parametrize(
        ("output_format", "pillow_format", "mime_type", "extension"),
        [
            ("png", "PNG", "image/png", "png"),
            ("jpeg", "JPEG", "image/jpeg", "jpg"),
            ("webp", "WEBP", "image/webp", "webp"),
        ],
    )
    async def test_the_stored_file_is_in_the_chosen_format(
        self, output_format: str, pillow_format: str, mime_type: str, extension: str
    ) -> None:
        caller = _caller(
            _qwen_options(), quality="standard", size="1024x1024", output_format=output_format
        )
        rows: list[dict[str, Any]] = []

        class _Repository:
            def __init__(self, _db: object) -> None:
                pass

            async def create(self, row: dict[str, Any]) -> Any:
                rows.append(row)
                return SimpleNamespace(id=uuid.uuid4(), expires_at=row["expires_at"])

        @asynccontextmanager
        async def _db_context() -> AsyncIterator[AsyncMock]:
            yield AsyncMock()

        vendor_png = io.BytesIO()
        Image.new("RGBA", (32, 32), (200, 30, 30, 128)).save(vendor_png, format="PNG")
        write = AsyncMock()
        with (
            patch.object(image_generation_tools, "_write_image_file", write),
            patch("src.domains.attachments.repository.AttachmentRepository", _Repository),
            patch("src.infrastructure.database.session.get_db_context", _db_context),
            patch("src.domains.image_generation.image_store.store_pending_image"),
        ):
            url = await image_generation_tools._save_image(
                vendor_png.getvalue(), caller=caller, prompt="a cat", filename_prefix="generated"
            )

        assert isinstance(url, str) and url.startswith("/api/v1/attachments/")
        assert write.await_args is not None
        written, relative_path = write.await_args.args
        assert Image.open(io.BytesIO(written)).format == pillow_format
        (row,) = rows
        assert (row["mime_type"], row["file_size"]) == (mime_type, len(written))
        assert row["stored_filename"].endswith(f".{extension}")
        assert relative_path.endswith(f".{extension}")
        assert row["original_filename"] == f"generated_{row['stored_filename']}"
