"""LangChain tools for AI image generation and editing.

Provides:
- generate_image: Creates images from text descriptions.
- edit_image: Edits an existing image (generated or uploaded attachment)
  using the OpenAI Responses API "Generate vs Edit" approach (no masks).

Architecture:
- User preferences (quality, size, format) from User model
- Model/provider from admin LLM Config (LLMConfigOverrideCache)
- Cost tracking via TrackingContext (ImageGenerationRecord)
- Image storage via AttachmentService (disk + DB, TTL-based cleanup)
- Image display via done metadata → frontend card

Phase: evolution — AI Image Generation
Created: 2026-03-25
"""

import base64
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.constants import (
    IMAGE_GENERATION_LLM_TYPE,
    IMAGE_GENERATION_VALID_QUALITIES,
    IMAGE_GENERATION_VALID_SIZES,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import registered_tool
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


@registered_tool
async def generate_image(
    prompt: str,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Generate an image from a text description using AI (e.g., gpt-image-1).

    Creates a single image based on the provided text prompt.
    Quality and size are controlled by the user's preferences in Settings.
    The generated image is displayed as a card below the assistant response.

    Args:
        prompt: Detailed text description of the image to generate.
            Be specific about style, content, colors, and composition.
    """
    start_time = time.time()

    # --- 1. Extract runtime context ---
    configurable = runtime.config.get("configurable", {}) if runtime else {}
    user_id_raw = configurable.get("user_id")

    if not user_id_raw:
        logger.warning("image_generation_no_user_id", has_runtime=runtime is not None)
        return UnifiedToolOutput.failure(
            message="Could not identify user. Please try again.",
            error_code="AUTH_ERROR",
        )

    # --- 2. Check global feature flag ---
    if not settings.image_generation_enabled:
        return UnifiedToolOutput.failure(
            message="Image generation is currently disabled by the administrator.",
            error_code="TOOL_ERROR",
        )

    # --- 3. Load user preferences from DB ---
    from src.domains.agents.tools.runtime_helpers import parse_user_id
    from src.infrastructure.database.session import get_db_context

    user_id = parse_user_id(user_id_raw)

    try:
        from src.domains.auth.models import User

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

            # User preferences ALWAYS take priority over planner-supplied values
            # to ensure cost control (the user defines their budget via settings)
            effective_quality = user.image_generation_default_quality
            effective_size = user.image_generation_default_size

    except Exception as e:
        logger.error("image_generation_user_prefs_error", error=str(e), user_id=str(user_id))
        return UnifiedToolOutput.failure(
            message="Error loading user preferences. Please try again.",
            error_code="TOOL_ERROR",
        )

    # --- 4. Resolve provider + model from admin LLM config ---
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_DEFAULTS

    override = LLMConfigOverrideCache.get_override(IMAGE_GENERATION_LLM_TYPE) or {}
    effective_provider = (
        override.get("provider") or LLM_DEFAULTS[IMAGE_GENERATION_LLM_TYPE].provider
    )
    effective_model = override.get("model") or LLM_DEFAULTS[IMAGE_GENERATION_LLM_TYPE].model

    # --- 5. Validate inputs ---
    if effective_quality not in IMAGE_GENERATION_VALID_QUALITIES:
        return UnifiedToolOutput.failure(
            message=(
                f"Invalid image quality '{effective_quality}'. "
                f"Must be one of: {', '.join(IMAGE_GENERATION_VALID_QUALITIES)}"
            ),
            error_code="TOOL_ERROR",
        )
    if effective_size not in IMAGE_GENERATION_VALID_SIZES:
        return UnifiedToolOutput.failure(
            message=(
                f"Invalid image size '{effective_size}'. "
                f"Must be one of: {', '.join(IMAGE_GENERATION_VALID_SIZES)}"
            ),
            error_code="TOOL_ERROR",
        )

    # --- 6. Generate image via provider-agnostic factory ---
    api_start = time.time()
    try:
        from src.domains.image_generation.client import create_image_client

        client = create_image_client(effective_provider)
        results = await client.generate(
            prompt=prompt,
            model=effective_model,
            quality=effective_quality,
            size=effective_size,
            n=1,
        )
    except ValueError as e:
        return UnifiedToolOutput.failure(
            message=f"Image generation error: {e}", error_code="TOOL_ERROR"
        )
    except Exception as e:
        logger.error(
            "image_generation_api_error",
            provider=effective_provider,
            model=effective_model,
            error_type=type(e).__name__,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=f"Image generation failed: {type(e).__name__}: {e}",
            error_code="TOOL_ERROR",
        )
    api_duration_ms = (time.time() - api_start) * 1000

    if not results or not results[0].b64_data:
        return UnifiedToolOutput.failure(
            message="Image generation returned empty result. Please try again.",
            error_code="TOOL_ERROR",
        )

    # --- 7. Track cost ---
    from src.domains.image_generation.tracker import track_image_generation_call

    track_image_generation_call(
        model=results[0].model,
        quality=effective_quality,
        size=effective_size,
        image_count=1,
        prompt=prompt,
        duration_ms=api_duration_ms,
    )

    # --- 8. Save image as Attachment (disk + DB, TTL-based cleanup) ---
    try:
        image_bytes = base64.b64decode(results[0].b64_data)
        stored_filename = f"{uuid.uuid4()}.png"
        relative_path = f"{user_id}/{stored_filename}"
        absolute_path = Path(settings.attachments_storage_path) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(image_bytes)

        from src.domains.attachments.models import (
            AttachmentContentType,
            AttachmentStatus,
        )
        from src.domains.attachments.repository import AttachmentRepository

        async with get_db_context() as db:
            repo = AttachmentRepository(db)
            attachment = await repo.create(
                {
                    "user_id": user_id,
                    "original_filename": f"generated_{stored_filename}",
                    "stored_filename": stored_filename,
                    "mime_type": "image/png",
                    "file_size": len(image_bytes),
                    "file_path": relative_path,
                    "content_type": AttachmentContentType.IMAGE,
                    "status": AttachmentStatus.READY,
                    "expires_at": datetime.now(UTC)
                    + timedelta(
                        hours=settings.attachments_ttl_hours,
                    ),
                }
            )
            await db.commit()
            attachment_id = str(attachment.id)

        image_url = f"/api/v1/attachments/{attachment_id}"

        # Store URL for delivery to frontend via done chunk metadata.
        # The streaming layer includes pending images in the done metadata
        # so the frontend renders them as cards below the assistant message.
        from src.domains.image_generation.image_store import store_pending_image

        conversation_id = configurable.get("thread_id", "unknown")
        store_pending_image(
            conversation_id=str(conversation_id),
            url=image_url,
            alt_text=prompt,
        )

        logger.info(
            "image_generation_attachment_saved",
            attachment_id=attachment_id,
            user_id=str(user_id),
            file_size=len(image_bytes),
            stored_path=relative_path,
        )

    except Exception as e:
        logger.error(
            "image_generation_save_error",
            error_type=type(e).__name__,
            error=str(e),
            user_id=str(user_id),
        )
        return UnifiedToolOutput.failure(
            message="Image was generated but could not be saved. Please try again.",
            error_code="TOOL_ERROR",
        )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "image_generation_tool_success",
        provider=effective_provider,
        model=effective_model,
        quality=effective_quality,
        size=effective_size,
        duration_ms=duration_ms,
        prompt_length=len(prompt),
        attachment_id=attachment_id,
    )

    # --- 9. Return structured response for orchestrator ---
    # UnifiedToolOutput.action_success() ensures the parallel_executor and
    # adaptive_replanner correctly recognise this as a successful action
    # (not an "empty result") and propagate the confirmation message to
    # response_node so the LLM knows the image was generated.
    revised = results[0].revised_prompt
    revised_note = f" Revised prompt: '{revised[:150]}'" if revised else ""
    return UnifiedToolOutput.action_success(
        message=(
            f"Image generated successfully and will be displayed automatically.{revised_note}\n"
            f"Do NOT include any markdown image link — the image is already shown to the user."
        ),
        structured_data={
            "image_url": image_url,
            "prompt": prompt[:200],
            "quality": effective_quality,
            "size": effective_size,
            "revised_prompt": revised[:200] if revised else None,
        },
    )


@registered_tool
async def edit_image(
    prompt: str,
    source_attachment_id: str = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Edit an existing image based on a text description using AI.

    Modifies the most recent image in the conversation (generated or uploaded).
    If source_attachment_id is provided and is a valid UUID, uses that specific image.
    Otherwise, automatically resolves the last image attachment of the user.
    Quality is controlled by the user's preferences in Settings.
    Size is auto-detected from source image proportions.

    Args:
        prompt: Detailed text description of the desired modification.
            Be specific about what to change, add, or remove.
        source_attachment_id: Optional UUID of a specific attachment to edit.
            If empty or not a valid UUID, the most recent image is used automatically.
    """
    start_time = time.time()

    # --- 1. Extract runtime context ---
    configurable = runtime.config.get("configurable", {}) if runtime else {}
    user_id_raw = configurable.get("user_id")

    if not user_id_raw:
        return UnifiedToolOutput.failure(
            message="Could not identify user.", error_code="TOOL_ERROR"
        )

    # --- 2. Feature flags ---
    if not settings.image_generation_enabled:
        return UnifiedToolOutput.failure(
            message="Image generation is currently disabled by the administrator.",
            error_code="TOOL_ERROR",
        )

    from src.domains.agents.tools.runtime_helpers import parse_user_id
    from src.infrastructure.database.session import get_db_context

    user_id = parse_user_id(user_id_raw)

    # --- 3. Load user preferences ---
    try:
        from src.domains.auth.models import User

        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if not user:
                return UnifiedToolOutput.failure(message="User not found.", error_code="TOOL_ERROR")
            if not user.image_generation_enabled:
                return UnifiedToolOutput.failure(
                    message="Image generation is not enabled in your settings.",
                    error_code="TOOL_ERROR",
                )
            # User preferences ALWAYS take priority for cost control
            effective_quality = user.image_generation_default_quality
    except Exception as e:
        logger.error("edit_image_user_prefs_error", error=str(e), user_id=str(user_id))
        return UnifiedToolOutput.failure(
            message="Error loading user preferences.", error_code="TOOL_ERROR"
        )

    # --- 4. Resolve source attachment (auto-detect if not a valid UUID) ---
    resolved_attachment_id: uuid.UUID | None = None

    # Try parsing as UUID first
    if source_attachment_id:
        try:
            resolved_attachment_id = uuid.UUID(source_attachment_id)
        except ValueError:
            logger.debug(
                "edit_image_invalid_uuid_fallback_to_latest",
                provided_value=source_attachment_id[:80],
                user_id=str(user_id),
            )

    # If no valid UUID, resolve the most recent image attachment for this user
    if resolved_attachment_id is None:
        try:
            from sqlalchemy import select

            from src.domains.attachments.models import (
                Attachment,
                AttachmentContentType,
                AttachmentStatus,
            )

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
                row = result.scalar_one_or_none()
                if row:
                    resolved_attachment_id = row
                    logger.info(
                        "edit_image_auto_resolved_latest",
                        attachment_id=str(resolved_attachment_id),
                        user_id=str(user_id),
                    )
        except Exception as e:
            logger.error("edit_image_auto_resolve_error", error=str(e))

    if resolved_attachment_id is None:
        return UnifiedToolOutput.failure(
            message="No image found to edit. Generate or upload an image first.",
            error_code="NOT_FOUND",
        )

    # --- 5. Load source image from disk ---
    try:
        from src.domains.attachments.service import AttachmentService

        async with get_db_context() as db:
            attachment_service = AttachmentService(db)
            attachment = await attachment_service.get_for_user(
                attachment_id=resolved_attachment_id,
                user_id=user_id,
            )
            source_path = Path(settings.attachments_storage_path) / attachment.file_path
            if not source_path.is_file():
                return UnifiedToolOutput.failure(
                    message="Source image file not found on disk.",
                    error_code="NOT_FOUND",
                )
            source_bytes = source_path.read_bytes()
            source_b64 = base64.b64encode(source_bytes).decode("ascii")
    except Exception as e:
        logger.error(
            "edit_image_source_load_error",
            error=str(e),
            attachment_id=str(resolved_attachment_id),
        )
        return UnifiedToolOutput.failure(
            message=f"Could not load source image: {e}",
            error_code="TOOL_ERROR",
        )

    # --- 5. Resize source image to reduce cost ---
    from src.domains.image_generation.resize import resize_image_b64

    # Auto-detect size from source image proportions
    resized_b64, effective_size = resize_image_b64(source_b64)

    # --- 6. Validate inputs ---
    if effective_quality not in IMAGE_GENERATION_VALID_QUALITIES:
        return UnifiedToolOutput.failure(
            message=f"Invalid quality '{effective_quality}'.",
            error_code="TOOL_ERROR",
        )
    if effective_size not in IMAGE_GENERATION_VALID_SIZES:
        return UnifiedToolOutput.failure(
            message=f"Invalid size '{effective_size}'.",
            error_code="TOOL_ERROR",
        )

    # --- 7. Resolve provider + models ---
    from src.core.constants import IMAGE_EDIT_RESPONSES_MODEL
    from src.domains.llm_config.cache import LLMConfigOverrideCache
    from src.domains.llm_config.constants import LLM_DEFAULTS

    override = LLMConfigOverrideCache.get_override(IMAGE_GENERATION_LLM_TYPE) or {}
    effective_provider = (
        override.get("provider") or LLM_DEFAULTS[IMAGE_GENERATION_LLM_TYPE].provider
    )
    # Image model (for pricing/cost tracking)
    effective_image_model = override.get("model") or LLM_DEFAULTS[IMAGE_GENERATION_LLM_TYPE].model
    # Text model for the Responses API (NOT the image model)
    responses_model = IMAGE_EDIT_RESPONSES_MODEL

    # --- 8. Call edit API ---
    api_start = time.time()
    try:
        from src.domains.image_generation.client import create_image_client

        client = create_image_client(effective_provider)
        results = await client.edit(
            prompt=prompt,
            source_image_b64=resized_b64,
            model=responses_model,
            quality=effective_quality,
            size=effective_size,
        )
    except ValueError as e:
        return UnifiedToolOutput.failure(message=f"Image edit error: {e}", error_code="TOOL_ERROR")
    except Exception as e:
        logger.error(
            "edit_image_api_error",
            provider=effective_provider,
            responses_model=responses_model,
            image_model=effective_image_model,
            error_type=type(e).__name__,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message=f"Image edit failed: {type(e).__name__}: {e}",
            error_code="TOOL_ERROR",
        )
    api_duration_ms = (time.time() - api_start) * 1000

    if not results or not results[0].b64_data:
        return UnifiedToolOutput.failure(
            message="Image edit returned empty result.", error_code="TOOL_ERROR"
        )

    # --- 9. Track cost (use IMAGE model for pricing, not the text model) ---
    from src.domains.image_generation.tracker import track_image_generation_call

    track_image_generation_call(
        model=effective_image_model,
        quality=effective_quality,
        size=effective_size,
        image_count=1,
        prompt=prompt,
        duration_ms=api_duration_ms,
    )

    # --- 10. Save edited image as Attachment ---
    try:
        image_bytes = base64.b64decode(results[0].b64_data)
        stored_filename = f"{uuid.uuid4()}.png"
        relative_path = f"{user_id}/{stored_filename}"
        absolute_path = Path(settings.attachments_storage_path) / relative_path
        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(image_bytes)

        from src.domains.attachments.models import (
            AttachmentContentType,
            AttachmentStatus,
        )
        from src.domains.attachments.repository import AttachmentRepository

        async with get_db_context() as db:
            repo = AttachmentRepository(db)
            new_attachment = await repo.create(
                {
                    "user_id": user_id,
                    "original_filename": f"edited_{stored_filename}",
                    "stored_filename": stored_filename,
                    "mime_type": "image/png",
                    "file_size": len(image_bytes),
                    "file_path": relative_path,
                    "content_type": AttachmentContentType.IMAGE,
                    "status": AttachmentStatus.READY,
                    "expires_at": datetime.now(UTC)
                    + timedelta(hours=settings.attachments_ttl_hours),
                }
            )
            await db.commit()
            attachment_id = str(new_attachment.id)

        image_url = f"/api/v1/attachments/{attachment_id}"

        from src.domains.image_generation.image_store import store_pending_image

        conversation_id = configurable.get("thread_id", "unknown")
        store_pending_image(
            conversation_id=str(conversation_id),
            url=image_url,
            alt_text=prompt,
        )

        logger.info(
            "edit_image_attachment_saved",
            attachment_id=attachment_id,
            user_id=str(user_id),
            file_size=len(image_bytes),
            source_attachment_id=source_attachment_id,
        )

    except Exception as e:
        logger.error(
            "edit_image_save_error",
            error_type=type(e).__name__,
            error=str(e),
        )
        return UnifiedToolOutput.failure(
            message="Image was edited but could not be saved.",
            error_code="TOOL_ERROR",
        )

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "edit_image_tool_success",
        provider=effective_provider,
        responses_model=responses_model,
        image_model=effective_image_model,
        quality=effective_quality,
        size=effective_size,
        duration_ms=duration_ms,
        source_attachment_id=source_attachment_id,
        attachment_id=attachment_id,
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
            "quality": effective_quality,
            "size": effective_size,
        },
    )
