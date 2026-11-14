"""A document's illustrations, drawn by the configured image model (ADR-274, ADR-305).

The writer asked for pictures — a deck's cover, its part openers, a content
slide; a report's cover and its illustration blocks — each by its subject in
English, in the one style the document shares. This module draws them, and
nothing else decides whether they exist:

- only what the normalized document still asks for, which the person's budget
  already bounded (``pictures.illustration_budget``);
- only when both spend ceilings answer yes (``spend_blocked``) — asked once,
  before the first picture, since a document may ask for six;
- at the person's quality, and in the billing tier of the size they chose, the
  frame deciding the proportions (``edit_size``);
- a few at a time (``DOCUMENT_ILLUSTRATION_CONCURRENCY``), each billed to the turn
  the moment the vendor bills it (``generate_billed``), all of them within one
  call's time of the image slot;
- without the prompt enhancement of ADR-315: the writer already wrote the prompt.

A picture that fails is left out, and its place is laid out without it; the
report says how many were drawn and why the others were not, by facts — a
status, a timeout — never by an error's words (ADR-303). A cancellation is not
caught: the pictures already billed stay billed, the others never were.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from PIL import Image

from src.core.constants import (
    DOCUMENT_ILLUSTRATION_CANCEL_GRACE_SECONDS,
    DOCUMENT_ILLUSTRATION_CONCURRENCY,
    DOCUMENT_ILLUSTRATION_DPI,
    DOCUMENT_ILLUSTRATION_JPEG_QUALITY,
    IMAGE_GENERATION_LLM_TYPE,
)
from src.core.document_preferences import DocumentPreferences
from src.core.llm_config_helper import llm_call_timeout_seconds
from src.domains.document_generation.pictures import (
    Frame,
    IllustrationRequest,
    Picture,
    illustration_budget,
)
from src.domains.document_generation.prompts import document_lines
from src.domains.document_generation.renderers import page_pictures
from src.domains.document_generation.renderers.pptx_pictures import picture_requests
from src.domains.document_generation.schemas import (
    DocumentContent,
    SectionedContent,
    SlideContent,
)
from src.domains.image_generation.billed_call import generate_billed
from src.domains.image_generation.encoding import flatten_to_rgb
from src.domains.image_generation.options_cache import ModelOptions
from src.domains.image_generation.preferences import (
    ImageModelNotServedError,
    active_image_options,
    edit_size,
    effective_quality,
    effective_size,
)
from src.domains.image_generation.providers.base import (
    ImageGenerationError,
    ImageProviderNotConfiguredError,
)
from src.domains.image_generation.sizing import ImageSize
from src.infrastructure.async_utils import cancel_and_wait
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Why a picture was not drawn, read from the failure's facts.
IllustrationFailure = Literal["refused", "rate_limited", "timed_out", "unavailable", "failed"]
#: Why no picture was attempted at all.
IllustrationSkip = Literal["usage_limit", "model_not_served"]
#: How many requests the gate's frame sizing reads per inch: proportions only.
_ASPECT_UNITS_PER_INCH = 100

#: The families that place pictures, and where each asks for them.
PICTURE_REQUESTS: Mapping[type, Callable[[DocumentContent], list[IllustrationRequest]]] = {
    SlideContent: lambda content: (
        picture_requests(content) if isinstance(content, SlideContent) else []
    ),
    SectionedContent: lambda content: (
        page_pictures.picture_requests(content) if isinstance(content, SectionedContent) else []
    ),
}


@dataclass(frozen=True, slots=True)
class IllustrationReport:
    """What became of the pictures a document asked for.

    Attributes:
        requested: The pictures the normalized document asked for.
        drawn: The pictures drawn and placed.
        failures: Why each picture that was attempted and not drawn failed.
        skipped: Why none was attempted, when none was.
    """

    requested: int = 0
    drawn: int = 0
    failures: tuple[IllustrationFailure, ...] = ()
    skipped: IllustrationSkip | None = None


def requests_for(content: DocumentContent) -> list[IllustrationRequest]:
    """The pictures a normalized document asks for, each subject drawn once per frame."""
    asking = PICTURE_REQUESTS.get(type(content))
    if asking is None:
        return []
    unique: dict[str, IllustrationRequest] = {}
    for request in asking(content):
        unique.setdefault(request.key, request)
    return list(unique.values())


def _failure(error: Exception) -> IllustrationFailure:
    """Classify a failure by its facts, never its words (ADR-303)."""
    if isinstance(error, ImageProviderNotConfiguredError):
        return "unavailable"
    if isinstance(error, ImageGenerationError):
        if error.timed_out:
            return "timed_out"
        if error.status_code == 429:
            return "rate_limited"
        if error.status_code is not None and 400 <= error.status_code < 500:
            return "refused"
    return "failed"


def image_prompt(subject: str, style: str) -> str:
    """What the image model receives: the subject, the deck's style, and no text drawn.

    Args:
        subject: The scene, in English.
        style: The deck's one style; empty takes the default.

    Returns:
        The prompt.
    """
    lines = document_lines()
    return lines["illustration.prompt"].format(
        subject=subject.rstrip(". "), style=style or lines["illustration.default_style"]
    )


def _crop_to(image: Image.Image, aspect: float) -> Image.Image:
    """The centre of the image at the frame's proportions."""
    width, height = image.size
    if width / height > aspect:
        kept = round(height * aspect)
        left = (width - kept) // 2
        return image.crop((left, 0, left + kept, height))
    kept = round(width / aspect)
    top = (height - kept) // 2
    return image.crop((0, top, width, top + kept))


def fit_to_frame(png: bytes, frame: Frame) -> Picture:
    """Crop a drawn image to its frame, resample it to the frame's size, write it as JPEG.

    Never enlarged: a picture smaller than its frame at the document resolution
    keeps its pixels, which an upscale would only multiply.

    Args:
        png: What the vendor returned.
        frame: The frame it fills.

    Returns:
        The picture, ready to be placed.
    """
    with Image.open(io.BytesIO(png)) as source:
        image = _crop_to(flatten_to_rgb(source), frame.aspect)
        target = (
            round(frame.width_in * DOCUMENT_ILLUSTRATION_DPI),
            round(frame.height_in * DOCUMENT_ILLUSTRATION_DPI),
        )
        if image.width > target[0]:
            image = image.resize(target, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=DOCUMENT_ILLUSTRATION_JPEG_QUALITY,
            optimize=True,
            progressive=True,
        )
        return Picture(buffer.getvalue(), image.width, image.height)


@dataclass(frozen=True, slots=True)
class _Order:
    """What every picture of one document is drawn with."""

    options: ModelOptions
    quality: str
    tier: str
    style: str
    gate: asyncio.Semaphore


async def _draw(request: IllustrationRequest, order: _Order) -> Picture | IllustrationFailure:
    """One picture, or why it is not drawn."""
    frame = ImageSize(
        round(request.frame.width_in * _ASPECT_UNITS_PER_INCH),
        round(request.frame.height_in * _ASPECT_UNITS_PER_INCH),
    )
    size = edit_size(frame, order.tier, order.options)
    async with order.gate:
        try:
            result = await generate_billed(
                order.options,
                prompt=image_prompt(request.subject, order.style),
                quality=order.quality,
                size=size,
            )
        except Exception as error:  # A failed picture never fails the document.
            failure = _failure(error)
            logger.warning(
                "document_illustration_failed",
                reason=failure,
                error_type=type(error).__name__,
                status_code=getattr(error, "status_code", None),
                frame=request.frame.name,
            )
            return failure
    try:
        return await asyncio.to_thread(fit_to_frame, result.png, request.frame)
    except Exception as error:  # Billed, but not an image a document can hold.
        logger.warning(
            "document_illustration_unreadable",
            error_type=type(error).__name__,
            frame=request.frame.name,
        )
        return "failed"


def _style(content: DocumentContent) -> str:
    return content.image_style if isinstance(content, SlideContent | SectionedContent) else ""


async def _within_one_call(
    requests: Sequence[IllustrationRequest], order: _Order
) -> list[Picture | IllustrationFailure]:
    """Draw the pictures, all of them within ONE call of the image slot.

    The tool's step is guaranteed one call per slot it declares (``TOOL_LLM_SLOTS``,
    ADR-221 amendment 2026-11-05); a document's pictures run in waves, so the waves
    share that call's time: what is drawn by then is kept, what is still drawing is
    cancelled and said ``timed_out`` — the document leaves without it rather than
    being lost with it. A cancellation of the caller takes every picture with it.
    """
    tasks = [asyncio.create_task(_draw(request, order)) for request in requests]
    try:
        _done, pending = await asyncio.wait(
            tasks, timeout=llm_call_timeout_seconds(IMAGE_GENERATION_LLM_TYPE)
        )
    except BaseException:
        for task in tasks:
            await cancel_and_wait(task, timeout_seconds=DOCUMENT_ILLUSTRATION_CANCEL_GRACE_SECONDS)
        raise
    for task in pending:
        await cancel_and_wait(task, timeout_seconds=DOCUMENT_ILLUSTRATION_CANCEL_GRACE_SECONDS)
        logger.warning("document_illustration_failed", reason="timed_out", deadline=True)
    return ["timed_out" if task in pending else task.result() for task in tasks]


async def draw_illustrations(
    content: DocumentContent, preferences: DocumentPreferences, *, user_id: uuid.UUID
) -> tuple[dict[str, Picture], IllustrationReport]:
    """Draw the pictures a normalized document asks for.

    Args:
        content: The normalized document; its pictures are within the budget.
        preferences: The person's document preferences (quality, size tier).
        user_id: Whose ceilings bound the spend, and whose turn is billed.

    Returns:
        The pictures by ``picture_key``, and what became of every request.
    """
    from src.domains.usage_limits.enforcement import spend_blocked

    requests = requests_for(content)[: illustration_budget(preferences)]
    if not requests:
        return {}, IllustrationReport()
    if await spend_blocked(user_id):
        return {}, IllustrationReport(requested=len(requests), skipped="usage_limit")
    try:
        options = active_image_options()
    except ImageModelNotServedError:
        logger.warning("document_illustrations_model_not_served", requested=len(requests))
        return {}, IllustrationReport(requested=len(requests), skipped="model_not_served")

    order = _Order(
        options=options,
        quality=effective_quality(preferences.image_quality, options),
        tier=effective_size(preferences.image_size, options),
        style=_style(content),
        gate=asyncio.Semaphore(DOCUMENT_ILLUSTRATION_CONCURRENCY),
    )
    outcomes = await _within_one_call(requests, order)
    pictures = {
        request.key: outcome
        for request, outcome in zip(requests, outcomes, strict=True)
        if isinstance(outcome, Picture)
    }
    failures = tuple(outcome for outcome in outcomes if not isinstance(outcome, Picture))
    logger.info(
        "document_illustrations_drawn",
        requested=len(requests),
        drawn=len(pictures),
        failed=len(failures),
    )
    return pictures, IllustrationReport(
        requested=len(requests), drawn=len(pictures), failures=failures
    )


__all__ = [
    "PICTURE_REQUESTS",
    "IllustrationFailure",
    "IllustrationReport",
    "IllustrationSkip",
    "draw_illustrations",
    "fit_to_frame",
    "image_prompt",
    "requests_for",
]
