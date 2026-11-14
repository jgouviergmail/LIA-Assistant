"""A document's illustrations: drawn within the budget, after the ceilings, honest about failures.

The vendor is replaced at the shared billed door (``generate_billed``), whose own
tests prove the bill; here the question is what the document asks for, what is
drawn, how many at once, and what the report says when a picture is not.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from src.core.config import settings
from src.core.constants import DOCUMENT_ILLUSTRATION_CONCURRENCY, DOCUMENT_ILLUSTRATION_DPI
from src.core.document_preferences import DocumentIllustrations, DocumentPreferences
from src.domains.document_generation import illustrations
from src.domains.document_generation.pictures import Frame, Picture, picture_key
from src.domains.document_generation.renderers.page_pictures import PAGE
from src.domains.document_generation.renderers.pptx_pictures import COVER, SECTION, SIDE, WIDE
from src.domains.document_generation.schemas import (
    Illustration,
    SectionBlock,
    SectionedContent,
    Slide,
    SlideContent,
    TableSheet,
    TabularContent,
)
from src.domains.image_generation.families import OPENAI_GPT_IMAGE
from src.domains.image_generation.options_cache import ModelOptions, QualityOption, SizeOption
from src.domains.image_generation.preferences import ImageModelNotServedError
from src.domains.image_generation.providers.base import (
    ImageGenerationError,
    ImageProviderNotConfiguredError,
    ImageResult,
)

pytestmark = pytest.mark.unit

_USER = uuid.UUID("44444444-4444-4444-8444-444444444444")
_ALLOWED = DocumentPreferences(images_allowed=True, image_quality="high", image_size="1536x1024")


def _png(width: int = 1536, height: int = 1024, mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    color: tuple[int, ...] = (200, 40, 40) if mode == "RGB" else (200, 40, 40, 0)
    Image.new(mode, (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _result(png: bytes | None = None) -> ImageResult:
    return ImageResult(png=png or _png(), model="image-model", provider="vendor")


def _offer() -> ModelOptions:
    return ModelOptions(
        model="image-model",
        provider="vendor",
        family=OPENAI_GPT_IMAGE,
        qualities=(
            QualityOption("low", Decimal("0.01"), Decimal("0.02")),
            QualityOption("high", Decimal("0.1"), Decimal("0.2")),
        ),
        sizes=(
            SizeOption("1024x1024", "square", None),
            SizeOption("1536x1024", "landscape", None),
            SizeOption("1024x1536", "portrait", None),
        ),
    )


def _deck(*subjects: str, cover: str | None = None) -> SlideContent:
    slides = [Slide(title=f"Part {index}", kind="section") for index in range(1)]
    slides += [
        Slide(title=f"Point {index}", bullets=["a"], illustration=Illustration(subject=subject))
        for index, subject in enumerate(subjects)
    ]
    return SlideContent(
        filename_stem="d",
        title="D",
        illustration=Illustration(subject=cover) if cover else None,
        image_style="watercolour, warm palette",
        slides=slides,
    )


def _report(*, cover: str | None = None, blocks: tuple[str, ...] = ()) -> SectionedContent:
    return SectionedContent(
        filename_stem="r",
        title="R",
        illustration=Illustration(subject=cover) if cover else None,
        image_style="ink drawing, muted palette",
        blocks=[
            SectionBlock(kind="paragraph", text="x"),
            *(
                SectionBlock(kind="illustration", illustration=Illustration(subject=subject))
                for subject in blocks
            ),
        ],
    )


class _Serving:
    """Patches the doors the production asks: the ceilings, the offer, the vendor."""

    def __init__(
        self,
        outcomes: list[ImageResult | Exception] | None = None,
        *,
        blocked: bool = False,
        offer: ModelOptions | Exception | None = None,
    ) -> None:
        self.outcomes = list(outcomes or [])
        self.blocked = blocked
        self.offer = offer if offer is not None else _offer()
        self.calls: list[dict[str, str]] = []

    async def generate(
        self, options: ModelOptions, *, prompt: str, quality: str, size: str
    ) -> ImageResult:
        self.calls.append({"prompt": prompt, "quality": quality, "size": size})
        outcome = self.outcomes.pop(0) if self.outcomes else _result()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def offered(self) -> ModelOptions:
        if isinstance(self.offer, Exception):
            raise self.offer
        return self.offer

    async def draw(
        self, content: SlideContent | SectionedContent, preferences: DocumentPreferences
    ) -> tuple[dict[str, Picture], illustrations.IllustrationReport]:
        with (
            patch.object(illustrations, "generate_billed", self.generate),
            patch.object(illustrations, "active_image_options", self.offered),
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked",
                AsyncMock(return_value=self.blocked),
            ),
        ):
            return await illustrations.draw_illustrations(content, preferences, user_id=_USER)


class TestWhatADocumentAsksFor:
    def test_each_place_asks_for_its_frame(self) -> None:
        deck = SlideContent(
            filename_stem="d",
            title="D",
            illustration=Illustration(subject="a city"),
            slides=[
                Slide(title="P", kind="section", illustration=Illustration(subject="a road")),
                Slide(title="C", bullets=["a"], illustration=Illustration(subject="a bridge")),
            ],
        )

        requests = illustrations.requests_for(deck)

        assert [(r.subject, r.frame.name) for r in requests] == [
            ("a city", COVER.frame.name),
            ("a road", SECTION.frame.name),
            ("a bridge", SIDE.frame.name),
        ]

    def test_a_slide_with_no_points_asks_for_the_wide_frame(self) -> None:
        deck = SlideContent(
            filename_stem="d",
            title="D",
            slides=[Slide(title="The view", illustration=Illustration(subject="a valley"))],
        )
        (request,) = illustrations.requests_for(deck)
        assert request.frame.name == WIDE.frame.name

    def test_one_subject_is_drawn_once_per_frame(self) -> None:
        requests = illustrations.requests_for(_deck("a bridge", "a bridge", "a tunnel"))
        assert [r.subject for r in requests] == ["a bridge", "a tunnel"]

    def test_a_report_asks_for_its_cover_then_its_blocks_in_one_frame(self) -> None:
        report = _report(cover="a city", blocks=("a road",))

        requests = illustrations.requests_for(report)

        assert [(r.subject, r.frame.name) for r in requests] == [
            ("a city", PAGE.name),
            ("a road", PAGE.name),
        ]

    def test_a_family_that_places_no_picture_asks_for_none(self) -> None:
        sheet = TabularContent(
            filename_stem="s",
            title="S",
            sheets=[TableSheet(name="t", headers=["a"], rows=[["1"]])],
        )
        assert illustrations.requests_for(sheet) == []


class TestDrawing:
    async def test_every_picture_is_drawn_to_its_frame_and_reported(self) -> None:
        serving = _Serving()

        pictures, report = await serving.draw(_deck("a bridge", cover="a city"), _ALLOWED)

        assert report == illustrations.IllustrationReport(requested=2, drawn=2)
        cover = pictures[picture_key(COVER.frame.name, "a city")]
        assert cover.data[:3] == b"\xff\xd8\xff"
        assert abs(cover.width_px / cover.height_px - COVER.frame.aspect) < 0.01
        assert cover.height_px <= round(COVER.frame.height_in * DOCUMENT_ILLUSTRATION_DPI)

    async def test_the_person_s_quality_and_size_tier_are_kept_the_frame_decides_the_shape(
        self,
    ) -> None:
        serving = _Serving()

        await serving.draw(_deck(cover="a city"), _ALLOWED)

        (call,) = serving.calls
        assert call["quality"] == "high"
        assert call["size"] == "1024x1536"  # the cover is a tall panel

    async def test_the_prompt_carries_the_style_and_forbids_drawn_text(self) -> None:
        serving = _Serving()

        await serving.draw(_deck("a bridge at dusk."), _ALLOWED)

        prompt = serving.calls[0]["prompt"]
        assert prompt.startswith("a bridge at dusk. Visual style: watercolour, warm palette.")
        assert "No text" in prompt

    async def test_a_report_s_pictures_share_its_style_in_a_photograph_s_shape(self) -> None:
        serving = _Serving()

        pictures, report = await serving.draw(_report(cover="a city"), _ALLOWED)

        (call,) = serving.calls
        assert "Visual style: ink drawing, muted palette." in call["prompt"]
        assert call["size"] == "1536x1024"  # a 3:2 frame across the page
        picture = pictures[picture_key(PAGE.name, "a city")]
        assert abs(picture.width_px / picture.height_px - PAGE.aspect) < 0.01
        assert report == illustrations.IllustrationReport(requested=1, drawn=1)

    async def test_no_budget_draws_nothing_and_asks_nobody(self) -> None:
        serving = _Serving()
        never = DocumentPreferences(images_allowed=True, illustrations=DocumentIllustrations.NEVER)

        pictures, report = await serving.draw(_deck("a bridge"), never)

        assert (pictures, report) == ({}, illustrations.IllustrationReport())
        assert serving.calls == []

    async def test_a_document_never_asks_for_more_than_the_budget(self) -> None:
        serving = _Serving()
        subjects = [f"scene {index}" for index in range(settings.document_illustrations_max + 2)]

        _pictures, report = await serving.draw(_deck(*subjects), _ALLOWED)

        assert report.requested == settings.document_illustrations_max
        assert len(serving.calls) == settings.document_illustrations_max


class TestWhatStopsThePictures:
    async def test_a_reached_ceiling_skips_them_all_before_any_spend(self) -> None:
        serving = _Serving(blocked=True)

        pictures, report = await serving.draw(_deck("a bridge", cover="a city"), _ALLOWED)

        assert pictures == {}
        assert report == illustrations.IllustrationReport(requested=2, skipped="usage_limit")
        assert serving.calls == []

    async def test_a_model_no_family_serves_skips_them_all(self) -> None:
        serving = _Serving(offer=ImageModelNotServedError("not served"))

        _pictures, report = await serving.draw(_deck("a bridge"), _ALLOWED)

        assert report == illustrations.IllustrationReport(requested=1, skipped="model_not_served")

    @pytest.mark.parametrize(
        ("error", "reason"),
        [
            (ImageGenerationError("busy", status_code=429), "rate_limited"),
            (ImageGenerationError("slow", timed_out=True), "timed_out"),
            (ImageGenerationError("no", status_code=400, vendor_code="blocked"), "refused"),
            (ImageProviderNotConfiguredError("no key"), "unavailable"),
            (ImageGenerationError("vendor down", status_code=503), "failed"),
            (RuntimeError("defect"), "failed"),
        ],
    )
    async def test_a_failed_picture_is_left_out_and_said_by_its_facts(
        self, error: Exception, reason: str
    ) -> None:
        serving = _Serving([error, _result()])

        pictures, report = await serving.draw(_deck("a bridge", "a tunnel"), _ALLOWED)

        assert report.requested == 2 and report.drawn == 1
        assert report.failures == (reason,)
        assert list(pictures) == [picture_key(SIDE.frame.name, "a tunnel")]

    async def test_an_image_no_reader_can_open_is_a_failure(self) -> None:
        serving = _Serving([_result(b"\x89PNG\r\n\x1a\nnot really")])

        pictures, report = await serving.draw(_deck("a bridge"), _ALLOWED)

        assert pictures == {} and report.failures == ("failed",)


class TestHowManyAtOnce:
    async def test_the_vendor_is_asked_a_few_at_a_time(self) -> None:
        active = 0
        peak = 0

        async def slow(
            options: ModelOptions, *, prompt: str, quality: str, size: str
        ) -> ImageResult:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return _result()

        subjects = [f"scene {index}" for index in range(settings.document_illustrations_max)]
        with (
            patch.object(illustrations, "generate_billed", slow),
            patch.object(illustrations, "active_image_options", _offer),
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked",
                AsyncMock(return_value=False),
            ),
        ):
            _pictures, report = await illustrations.draw_illustrations(
                _deck(*subjects), _ALLOWED, user_id=_USER
            )

        assert report.drawn == len(subjects)
        assert peak == min(DOCUMENT_ILLUSTRATION_CONCURRENCY, len(subjects))

    async def test_the_pictures_share_one_call_s_time_and_a_late_one_is_left_out(
        self,
    ) -> None:
        cancelled: list[str] = []

        async def uneven(
            options: ModelOptions, *, prompt: str, quality: str, size: str
        ) -> ImageResult:
            if prompt.startswith("a slow scene"):
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    cancelled.append(prompt)
                    raise
            return _result()

        with (
            patch.object(illustrations, "generate_billed", uneven),
            patch.object(illustrations, "active_image_options", _offer),
            patch.object(illustrations, "llm_call_timeout_seconds", lambda slot: 0.2),
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked",
                AsyncMock(return_value=False),
            ),
        ):
            pictures, report = await illustrations.draw_illustrations(
                _deck("a quick scene", "a slow scene"), _ALLOWED, user_id=_USER
            )

        assert list(pictures) == [picture_key(SIDE.frame.name, "a quick scene")]
        assert report == illustrations.IllustrationReport(
            requested=2, drawn=1, failures=("timed_out",)
        )
        assert len(cancelled) == 1  # stopped, not abandoned mid-flight

    async def test_a_cancellation_is_never_swallowed(self) -> None:
        started = asyncio.Event()

        async def hanging(
            options: ModelOptions, *, prompt: str, quality: str, size: str
        ) -> ImageResult:
            started.set()
            await asyncio.sleep(3600)
            return _result()

        with (
            patch.object(illustrations, "generate_billed", hanging),
            patch.object(illustrations, "active_image_options", _offer),
            patch(
                "src.domains.usage_limits.enforcement.spend_blocked",
                AsyncMock(return_value=False),
            ),
        ):
            task = asyncio.create_task(
                illustrations.draw_illustrations(_deck("a bridge"), _ALLOWED, user_id=_USER)
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


class TestFittingAPicture:
    def test_it_is_cropped_to_its_frame_and_never_enlarged(self) -> None:
        frame = Frame("side", 4.0, 5.0)

        small = illustrations.fit_to_frame(_png(400, 400), frame)
        large = illustrations.fit_to_frame(_png(2000, 1500), frame)

        assert (small.width_px, small.height_px) == (320, 400)
        assert (large.width_px, large.height_px) == (
            round(4.0 * DOCUMENT_ILLUSTRATION_DPI),
            round(5.0 * DOCUMENT_ILLUSTRATION_DPI),
        )

    def test_a_transparent_drawing_is_laid_on_white(self) -> None:
        picture = illustrations.fit_to_frame(_png(300, 300, mode="RGBA"), Frame("f", 2.0, 2.0))

        with Image.open(io.BytesIO(picture.data)) as image:
            assert image.mode == "RGB"
            assert image.getpixel((10, 10)) == (255, 255, 255)

    def test_the_default_style_stands_in_for_none(self) -> None:
        prompt = illustrations.image_prompt("a harbour", "")
        assert "Visual style: clean editorial illustration" in prompt
