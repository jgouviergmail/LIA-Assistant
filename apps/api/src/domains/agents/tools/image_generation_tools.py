"""LangChain tools for AI image generation and editing (ADR-305).

Provides:
- generate_image: Creates an image from a text description.
- edit_image: Produces an image from an existing one (generated or uploaded) and
  an instruction.

Architecture:
- The configured image model (admin LLM Config) and what it offers come from
  ``image_generation.preferences.active_image_options`` — a model no family and
  client serve is refused with its reason, never attempted.
- The person's stored quality and size are intents mapped onto that offer by the
  same resolver the settings page reads (``effective_quality`` / ``effective_size``
  / ``edit_size``).
- One client per provider (``image_generation.client``), used as an async context
  manager so its transport closes on this loop.
- Cost tracking via TrackingContext (ImageGenerationRecord): output images, plus
  the reference image of an edit where the family bills it per image.
- Image storage via the attachments table (disk + DB, TTL-based cleanup), in the
  format the person chose (``image_generation.encoding``), shown through the done
  metadata as a card.

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.domains.agents.constants import AGENT_IMAGE
from src.domains.agents.context.runtime_context import (
    LiaRuntimeContext,
    tool_user_id_str,
)
from src.domains.agents.tools.common import ToolErrorCode, http_status_to_error_code
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.domains.attachments.urls import attachment_url
from src.domains.image_generation.options_cache import ModelOptions
from src.domains.image_generation.providers.base import (
    ImageDeliveryError,
    ImageGenerationClient,
    ImageGenerationError,
    ImageProviderNotConfiguredError,
    ImageResult,
)
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = get_logger(__name__)

_ProviderCall = Callable[[ImageGenerationClient], Awaitable[ImageResult]]
#: Records the cost of a call the vendor billed, given its duration in ms.
_Bill = Callable[[float], None]


@dataclass(frozen=True)
class _Caller:
    """Who asked, what they prefer, and what the configured model offers."""

    user_id: uuid.UUID
    thread_id: str | None
    stored_quality: str | None
    stored_size: str | None
    options: ModelOptions
    output_format: str
    #: The person asked for their generation prompts to be enhanced (ADR-315).
    enhance_prompt: bool = False


async def _write_image_file(image_bytes: bytes, relative_path: str) -> Path:
    """Persist generated image bytes under the attachments storage root.

    The (potentially multi-MB) disk write is offloaded to a worker thread so it
    never blocks the event loop during a generation (CA-4). The parent
    directory is created eagerly (a cheap single ``mkdir``).

    Args:
        image_bytes: The encoded image to persist.
        relative_path: Path relative to ``attachments_storage_path``
            (e.g. ``"<user_id>/<uuid>.png"``).

    Returns:
        The absolute path the bytes were written to.
    """
    absolute_path = Path(settings.attachments_storage_path) / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, image_bytes)
    return absolute_path


async def _resolve_caller(
    runtime: ToolRuntime[LiaRuntimeContext, Any] | None, tool: str
) -> _Caller | UnifiedToolOutput:
    """The caller, their preferences and the configured model's offer.

    Args:
        runtime: The tool runtime.
        tool: The tool's name, for logs.

    Returns:
        The caller, or the failure to hand back to the model.
    """
    from src.domains.agents.tools.runtime_helpers import parse_user_id
    from src.domains.image_generation.preferences import (
        ImageModelNotServedError,
        active_image_options,
    )
    from src.domains.users.models import User
    from src.infrastructure.database.session import get_db_context

    user_id_raw = tool_user_id_str(runtime)
    if not user_id_raw:
        logger.warning("image_tool_no_user_id", tool=tool, has_runtime=runtime is not None)
        return UnifiedToolOutput.failure(
            message="Could not identify user. Please try again.", error_code="AUTH_ERROR"
        )
    if not settings.image_generation_enabled:
        return UnifiedToolOutput.failure(
            message="Image generation is currently disabled by the administrator.",
            error_code="TOOL_ERROR",
        )

    user_id = parse_user_id(user_id_raw)
    try:
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if not user:
                return UnifiedToolOutput.failure(message="User not found.", error_code="TOOL_ERROR")
            if not user.image_generation_enabled:
                return UnifiedToolOutput.failure(
                    message=(
                        "Image generation is not enabled in your settings. "
                        "Enable it in Settings > Features > Image Generation."
                    ),
                    error_code="TOOL_ERROR",
                )
            stored_quality = user.image_generation_default_quality
            stored_size = user.image_generation_default_size
            output_format = user.image_generation_output_format
            enhance_prompt = user.image_generation_prompt_enhancement
    except Exception as e:
        logger.error("image_tool_user_prefs_error", tool=tool, error_type=type(e).__name__)
        return UnifiedToolOutput.failure(
            message="Error loading user preferences. Please try again.",
            error_code="TOOL_ERROR",
        )

    try:
        options = active_image_options()
    except ImageModelNotServedError as e:
        logger.warning("image_tool_model_not_served", tool=tool)
        return UnifiedToolOutput.failure(message=str(e), error_code="TOOL_ERROR")

    configurable = runtime.config.get("configurable", {}) if runtime else {}
    thread_id = configurable.get("thread_id")
    return _Caller(
        user_id=user_id,
        thread_id=str(thread_id) if thread_id else None,
        stored_quality=stored_quality,
        stored_size=stored_size,
        options=options,
        output_format=output_format,
        enhance_prompt=bool(enhance_prompt),
    )


async def _prompt_for_the_model(
    prompt: str, caller: _Caller, runtime: ToolRuntime[LiaRuntimeContext, Any] | None
) -> str:
    """The request as the image model receives it (ADR-315).

    Enhanced when the person turned it on AND the operator offers it; the
    original otherwise, and on any doubt the enhancement has — it never costs
    the person their image.

    Args:
        prompt: The request the tool received.
        caller: Who asked, and whether they want their prompts enhanced.
        runtime: The tool runtime; its config carries the turn's tracker.

    Returns:
        The prompt to send to the image model.
    """
    from src.domains.agents.image_generation.prompt_enhancement import enhance_image_prompt
    from src.domains.image_generation.preferences import prompt_enhancement_offered

    if not (caller.enhance_prompt and prompt_enhancement_offered()):
        return prompt
    enhancement = await enhance_image_prompt(
        prompt, user_id=str(caller.user_id), config=runtime.config if runtime else None
    )
    return enhancement.text


def _failure_code(error: ImageGenerationError) -> ToolErrorCode:
    """Classify a client failure by its facts, in the shared taxonomy (ADR-303).

    A vendor status goes through the one HTTP classifier every tool shares, so a
    throttled call reads « retry later » and a refused prompt « the request was
    refused », never a generic tool error.
    """
    if isinstance(error, ImageProviderNotConfiguredError):
        return ToolErrorCode.CONFIGURATION_ERROR
    if error.timed_out:
        return ToolErrorCode.TIMEOUT
    if error.status_code is not None:
        return http_status_to_error_code(error.status_code)
    return ToolErrorCode.EXTERNAL_API_ERROR


async def _call_provider(
    options: ModelOptions, call: _ProviderCall, *, action: str, bill: _Bill
) -> ImageResult | UnifiedToolOutput:
    """Run one vendor call on the configured model's client, and bill what it cost.

    Args:
        options: The configured model's offer (its provider picks the client).
        call: What to ask the client.
        action: ``generation`` or ``edit``, for the messages and logs.
        bill: Records the call's cost; invoked for every image the vendor
            billed — delivered, or produced and lost on the way (ADR-272).

    Returns:
        The image, or the failure to hand back to the model. A failure log
        carries codes, never the message (ADR-303).
    """
    from src.domains.image_generation.client import create_image_client

    started = time.time()
    try:
        async with create_image_client(options.provider) as client:
            result = await call(client)
    except ImageGenerationError as e:
        billed = isinstance(e, ImageDeliveryError)
        if billed:
            bill((time.time() - started) * 1000)
        code = _failure_code(e)
        logger.warning(
            "image_tool_provider_failed",
            action=action,
            provider=options.provider,
            model=options.model,
            error_type=type(e).__name__,
            error_code=code.value,
            status_code=e.status_code,
            vendor_code=e.vendor_code,
            billed=billed,
        )
        return UnifiedToolOutput.failure(
            message=f"Image {action} error: {e}", error_code=code.value
        )
    except Exception as e:
        # A client translates its vendor's failures; anything else is a defect here.
        logger.error(
            "image_tool_provider_error",
            action=action,
            provider=options.provider,
            model=options.model,
            error_type=type(e).__name__,
        )
        return UnifiedToolOutput.failure(
            message=f"Image {action} failed unexpectedly ({type(e).__name__}).",
            error_code=ToolErrorCode.INTERNAL_ERROR.value,
        )
    bill((time.time() - started) * 1000)
    return result


async def _save_image(
    png: bytes, *, caller: _Caller, prompt: str, filename_prefix: str
) -> str | UnifiedToolOutput:
    """Store the image, in the person's format, and queue it for the done card.

    Args:
        png: The image the client returned.
        caller: Its owner, conversation and chosen output format.
        prompt: The request, which titles the image in the gallery (ADR-279).
        filename_prefix: ``generated`` or ``edited``.

    Returns:
        The image's URL, or the failure to hand back to the model.
    """
    from src.domains.attachments.models import (
        AttachmentContentType,
        AttachmentOrigin,
        AttachmentStatus,
    )
    from src.domains.attachments.repository import AttachmentRepository
    from src.domains.attachments.thread_id import conversation_uuid
    from src.domains.image_generation.encoding import encode_for_delivery_async
    from src.domains.image_generation.image_store import sanitize_alt_text, store_pending_image
    from src.infrastructure.database.session import get_db_context

    try:
        image = await encode_for_delivery_async(png, caller.output_format)
        stored_filename = f"{uuid.uuid4()}.{image.extension}"
        relative_path = f"{caller.user_id}/{stored_filename}"
        await _write_image_file(image.data, relative_path)

        async with get_db_context() as db:
            attachment = await AttachmentRepository(db).create(
                {
                    "user_id": caller.user_id,
                    "original_filename": f"{filename_prefix}_{stored_filename}",
                    "stored_filename": stored_filename,
                    "mime_type": image.mime_type,
                    "file_size": len(image.data),
                    "file_path": relative_path,
                    "content_type": AttachmentContentType.IMAGE,
                    # Named, so the person finds it again in their gallery
                    # after the conversation is reset (ADR-279).
                    "origin": AttachmentOrigin.GENERATED_IMAGE.value,
                    "title": sanitize_alt_text(prompt),
                    "conversation_id": conversation_uuid(caller.thread_id),
                    "status": AttachmentStatus.READY,
                    "expires_at": datetime.now(UTC)
                    + timedelta(hours=settings.attachments_ttl_hours),
                }
            )
            # Serialized here, next to the value that produced it: what leaves
            # this block is an ISO string, so no `datetime` ever reaches the SSE
            # payload or the JSONB metadata. (The session is created with
            # `expire_on_commit=False`, so reading before or after the commit is
            # equivalent — the line below reads `attachment.id` after it.)
            expires_at_iso = attachment.expires_at.isoformat() if attachment.expires_at else None
            await db.commit()
            attachment_id = str(attachment.id)
    except Exception as e:
        logger.error(
            "image_tool_save_error",
            prefix=filename_prefix,
            error_type=type(e).__name__,
            user_id=str(caller.user_id),
        )
        return UnifiedToolOutput.failure(
            message="The image was produced but could not be saved. Please try again.",
            error_code="TOOL_ERROR",
        )

    image_url = attachment_url(attachment_id)
    # Delivered to the frontend through the done chunk metadata, rendered as a
    # card below the assistant message.
    store_pending_image(
        conversation_id=caller.thread_id or "unknown",
        url=image_url,
        alt_text=prompt,
        expires_at=expires_at_iso,
    )
    logger.info(
        "image_tool_attachment_saved",
        prefix=filename_prefix,
        attachment_id=attachment_id,
        user_id=str(caller.user_id),
        mime_type=image.mime_type,
        file_size=len(image.data),
    )
    return image_url


@registered_tool
@track_tool_metrics(
    tool_name="generate_image",
    agent_name=AGENT_IMAGE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.image_generation_rate_limit_calls,
    window_seconds=lambda: settings.image_generation_rate_limit_window,
    scope="user",
)
async def generate_image(
    prompt: str,
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Generate an image from a text description using AI.

    Creates a single image based on the provided text prompt.
    Quality and size are controlled by the user's preferences in Settings.
    The generated image is displayed as a card below the assistant response.

    Args:
        prompt: Detailed text description of the image to generate.
            Be specific about style, content, colors, and composition.
    """
    from src.domains.image_generation.preferences import effective_quality, effective_size
    from src.domains.image_generation.tracker import track_image_generation_call

    start_time = time.time()
    caller = await _resolve_caller(runtime, "generate_image")
    if isinstance(caller, UnifiedToolOutput):
        return caller
    options = caller.options
    # The person's preferences, mapped onto what the configured model offers —
    # never a planner-supplied value: the settings are the person's budget.
    quality = effective_quality(caller.stored_quality, options)
    size = effective_size(caller.stored_size, options)
    # What the vendor receives and bills; the gallery keeps the person's words.
    sent_prompt = await _prompt_for_the_model(prompt, caller, runtime)

    result = await _call_provider(
        options,
        lambda client: client.generate(
            prompt=sent_prompt, model=options.model, quality=quality, size=size
        ),
        action="generation",
        bill=lambda duration_ms: track_image_generation_call(
            model=options.model,
            quality=quality,
            size=size,
            image_count=1,
            prompt=sent_prompt,
            duration_ms=duration_ms,
        ),
    )
    if isinstance(result, UnifiedToolOutput):
        return result

    image_url = await _save_image(
        result.png, caller=caller, prompt=prompt, filename_prefix="generated"
    )
    if isinstance(image_url, UnifiedToolOutput):
        return image_url

    logger.info(
        "image_generation_tool_success",
        provider=options.provider,
        model=options.model,
        quality=quality,
        size=size,
        duration_ms=int((time.time() - start_time) * 1000),
        prompt_length=len(prompt),
        prompt_enhanced=sent_prompt != prompt,
    )

    # action_success() lets the parallel executor and the adaptive replanner
    # recognise a successful action (not an "empty result") and hands the
    # confirmation to the response node.
    revised = result.revised_prompt
    revised_note = f" Revised prompt: '{revised[:150]}'" if revised else ""
    return UnifiedToolOutput.action_success(
        message=(
            f"Image generated successfully and will be displayed automatically.{revised_note}\n"
            f"Do NOT include any markdown image link — the image is already shown to the user."
        ),
        structured_data={
            "image_url": image_url,
            "prompt": prompt[:200],
            "quality": quality,
            "size": size,
            "revised_prompt": revised[:200] if revised else None,
        },
    )


async def _latest_image_attachment(user_id: uuid.UUID) -> uuid.UUID | None:
    """The person's most recent ready image attachment, if any."""
    from sqlalchemy import select

    from src.domains.attachments.models import (
        Attachment,
        AttachmentContentType,
        AttachmentStatus,
    )
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(Attachment.id)
                .where(
                    Attachment.user_id == user_id,
                    Attachment.content_type == AttachmentContentType.IMAGE,
                    Attachment.status == AttachmentStatus.READY,
                )
                .order_by(Attachment.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()
    except Exception as e:
        logger.error("edit_image_auto_resolve_error", error_type=type(e).__name__)
        return None


async def _load_source_bytes(attachment_id: uuid.UUID, user_id: uuid.UUID) -> bytes | None:
    """The stored bytes of an attachment the person owns, or ``None``."""
    from src.domains.attachments.service import AttachmentService
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        attachment = await AttachmentService(db).get_for_user(
            attachment_id=attachment_id, user_id=user_id
        )
        source_path = Path(settings.attachments_storage_path) / attachment.file_path
    if not source_path.is_file():
        return None
    return await asyncio.to_thread(source_path.read_bytes)


async def _resolve_source(
    source_attachment_id: str, user_id: uuid.UUID
) -> bytes | UnifiedToolOutput:
    """The edit's source image: the named attachment, else the latest image."""
    resolved: uuid.UUID | None = None
    if source_attachment_id:
        try:
            resolved = uuid.UUID(source_attachment_id)
        except ValueError:
            logger.debug(
                "edit_image_invalid_uuid_fallback_to_latest",
                provided_value=source_attachment_id[:80],
                user_id=str(user_id),
            )
    if resolved is None:
        resolved = await _latest_image_attachment(user_id)
        if resolved is not None:
            logger.info(
                "edit_image_auto_resolved_latest",
                attachment_id=str(resolved),
                user_id=str(user_id),
            )
    if resolved is None:
        return UnifiedToolOutput.failure(
            message="No image found to edit. Generate or upload an image first.",
            error_code="NOT_FOUND",
        )
    try:
        source_bytes = await _load_source_bytes(resolved, user_id)
    except Exception as e:
        logger.error(
            "edit_image_source_load_error",
            error_type=type(e).__name__,
            attachment_id=str(resolved),
        )
        return UnifiedToolOutput.failure(
            message=f"Could not load source image: {e}", error_code="TOOL_ERROR"
        )
    if source_bytes is None:
        return UnifiedToolOutput.failure(
            message="Source image file not found on disk.", error_code="NOT_FOUND"
        )
    return source_bytes


@registered_tool
@track_tool_metrics(
    tool_name="edit_image",
    agent_name=AGENT_IMAGE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: settings.image_generation_rate_limit_calls,
    window_seconds=lambda: settings.image_generation_rate_limit_window,
    scope="user",
)
async def edit_image(
    prompt: str,
    source_attachment_id: str = "",
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Edit an existing image based on a text description using AI.

    If source_attachment_id is provided and is a valid UUID, edits that image.
    Otherwise, edits the user's most recent image (generated or uploaded).
    Quality is controlled by the user's preferences in Settings.
    Size is auto-detected from source image proportions.

    Args:
        prompt: Detailed text description of the desired modification.
            Be specific about what to change, add, or remove.
        source_attachment_id: Optional UUID of a specific attachment to edit.
            If empty or not a valid UUID, the most recent image is used automatically.
    """
    from src.domains.image_generation.preferences import (
        edit_size,
        effective_quality,
        effective_size,
    )
    from src.domains.image_generation.resize import (
        prepare_source_image_async,
        read_oriented_size_async,
    )
    from src.domains.image_generation.sizing import ImageSize
    from src.domains.image_generation.tracker import track_image_generation_call

    start_time = time.time()
    caller = await _resolve_caller(runtime, "edit_image")
    if isinstance(caller, UnifiedToolOutput):
        return caller
    source_bytes = await _resolve_source(source_attachment_id, caller.user_id)
    if isinstance(source_bytes, UnifiedToolOutput):
        return source_bytes

    options = caller.options
    family = options.family
    quality = effective_quality(caller.stored_quality, options)
    try:
        displayed = await read_oriented_size_async(source_bytes)
        size = edit_size(displayed, effective_size(caller.stored_size, options), options)
        source = await prepare_source_image_async(
            source_bytes,
            box=family.source_box(ImageSize.parse(size)),
            max_bytes=family.source_max_bytes,
        )
    except ValueError as e:
        return UnifiedToolOutput.failure(
            message=f"The source image cannot be edited: {e}", error_code="TOOL_ERROR"
        )

    result = await _call_provider(
        options,
        lambda client: client.edit(
            prompt=prompt, source=source, model=options.model, quality=quality, size=size
        ),
        action="edit",
        # The edit sends ONE reference image; a family that bills it per image
        # prices it at the output's key (ADR-305).
        bill=lambda duration_ms: track_image_generation_call(
            model=options.model,
            quality=quality,
            size=size,
            image_count=1,
            input_image_count=1,
            prompt=prompt,
            duration_ms=duration_ms,
        ),
    )
    if isinstance(result, UnifiedToolOutput):
        return result

    image_url = await _save_image(
        result.png, caller=caller, prompt=prompt, filename_prefix="edited"
    )
    if isinstance(image_url, UnifiedToolOutput):
        return image_url

    logger.info(
        "edit_image_tool_success",
        provider=options.provider,
        model=options.model,
        quality=quality,
        size=size,
        duration_ms=int((time.time() - start_time) * 1000),
        source_attachment_id=source_attachment_id,
    )

    return UnifiedToolOutput.action_success(
        message=(
            "Image edited successfully and will be displayed automatically.\n"
            "Do NOT include any markdown image link — the image is already shown."
        ),
        structured_data={
            "image_url": image_url,
            "prompt": prompt[:200],
            "source_attachment_id": source_attachment_id,
            "quality": quality,
            "size": size,
        },
    )
