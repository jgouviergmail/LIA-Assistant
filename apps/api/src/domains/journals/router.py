"""
Journals router with FastAPI endpoints for journal entry management.

Provides CRUD operations and settings management for:
- Entry listing with size info and theme counts
- Manual entry creation
- Entry update and deletion
- Settings configuration (enable/disable, size limits)
- GDPR export and bulk delete
- Available themes listing

References:
    - Pattern: domains/interests/router.py
"""

import csv
import io
import json
from contextlib import suppress
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    JOURNAL_CONSOLIDATION_ENABLED_DEFAULT,
    JOURNAL_CONSOLIDATION_WITH_HISTORY_DEFAULT,
)
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.session_dependencies import get_current_active_session
from src.domains.journals.constants import JOURNAL_PORTRAIT_FEEDBACK_THEME
from src.domains.journals.models import JournalEntry, JournalEntrySource, JournalTheme
from src.domains.journals.schemas import (
    JournalConsolidationResponse,
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryUpdate,
    JournalPortraitFeedbackRequest,
    JournalPortraitResponse,
    JournalSettingsResponse,
    JournalSettingsUpdate,
    JournalThemeInfo,
    JournalThemesResponse,
    ThemeCount,
)
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/journals", tags=["Journals"])


# =============================================================================
# Helper functions
# =============================================================================


def _entry_to_response(entry: JournalEntry) -> JournalEntryResponse:
    """Convert JournalEntry model to API response.

    Args:
        entry: JournalEntry SQLAlchemy model instance.

    Returns:
        Validated JournalEntryResponse Pydantic schema.
    """
    return JournalEntryResponse.model_validate(entry)


def _build_theme_counts(theme_counts: dict[str, int], user_id: UUID) -> list[ThemeCount]:
    """Convert raw per-theme counts into validated response items.

    A theme string absent from :class:`JournalTheme` is skipped, not raised on:
    ``JournalTheme(unknown)`` raises ``ValueError``, which would turn a single
    unexpected row into a 500 on ``GET /journals`` — the whole journal page,
    not just one counter. Skipping keeps the page usable; the warning keeps the
    anomaly visible rather than silently swallowed.

    Args:
        theme_counts: Mapping of raw theme code to active entry count.
        user_id: Owner user UUID, for the anomaly log.

    Returns:
        One ``ThemeCount`` per recognised theme.
    """
    counts: list[ThemeCount] = []
    for raw_theme, count in theme_counts.items():
        try:
            theme = JournalTheme(raw_theme)
        except ValueError:
            logger.warning(
                "journal_unknown_theme_in_corpus",
                user_id=str(user_id),
                theme=raw_theme,
                count=count,
            )
            continue
        counts.append(ThemeCount(theme=theme, count=count))
    return counts


async def _build_settings_response(user: User, service: JournalService) -> JournalSettingsResponse:
    """Build full settings response with size and cost info.

    Args:
        user: Authenticated User model with journal_* fields.
        service: JournalService instance for size queries.

    Returns:
        Complete JournalSettingsResponse with size and cost info.
    """
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    size_info = await service.get_size_info(user.id, max_total_chars)
    last_cost = JournalService.build_cost_info_from_user(user)

    return JournalSettingsResponse(
        journals_enabled=getattr(user, "journals_enabled", settings.journals_enabled),
        journal_consolidation_enabled=getattr(
            user, "journal_consolidation_enabled", JOURNAL_CONSOLIDATION_ENABLED_DEFAULT
        ),
        journal_consolidation_with_history=getattr(
            user, "journal_consolidation_with_history", JOURNAL_CONSOLIDATION_WITH_HISTORY_DEFAULT
        ),
        journal_max_total_chars=max_total_chars,
        journal_context_max_chars=getattr(
            user, "journal_context_max_chars", settings.journal_default_context_max_chars
        ),
        journal_max_entry_chars=getattr(
            user, "journal_max_entry_chars", settings.journal_max_entry_chars
        ),
        journal_context_max_results=getattr(
            user, "journal_context_max_results", settings.journal_context_max_results
        ),
        size_info=size_info,
        last_cost=last_cost,
    )


# =============================================================================
# Themes Endpoint (static path — must be before /{entry_id} routes)
# =============================================================================


@router.get("/themes", response_model=JournalThemesResponse)
async def list_themes(
    user: User = Depends(get_current_active_session),
) -> JournalThemesResponse:
    """List available journal themes with labels."""
    return JournalThemesResponse(
        themes=[
            JournalThemeInfo(code=t.value, label=t.value.replace("_", " ").title())
            for t in JournalTheme
        ]
    )


# =============================================================================
# Settings Endpoints (static paths — must be before /{entry_id} routes)
# =============================================================================


@router.get("/settings", response_model=JournalSettingsResponse)
async def get_journal_settings(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalSettingsResponse:
    """Get user journal settings with size and cost info."""
    service = JournalService(db)
    return await _build_settings_response(user, service)


@router.patch("/settings", response_model=JournalSettingsResponse)
async def update_journal_settings(
    data: JournalSettingsUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalSettingsResponse:
    """Update user journal settings.

    Raises:
        ValidationError: If max_total_chars is set below current usage.
    """
    service = JournalService(db)
    update_data = data.model_dump(exclude_unset=True)

    # Validate max_total_chars >= current total
    if "journal_max_total_chars" in update_data:
        total_chars = await service.repo.get_total_chars(user.id)
        if update_data["journal_max_total_chars"] < total_chars:
            raise ValidationError(
                detail=(
                    f"Cannot set max_total_chars ({update_data['journal_max_total_chars']}) "
                    f"below current usage ({total_chars}). "
                    "Delete entries first to reduce usage."
                )
            )

    if update_data:
        for field_name, value in update_data.items():
            setattr(user, field_name, value)
        await db.commit()

    return await _build_settings_response(user, service)


# =============================================================================
# Export Endpoint (static path — must be before /{entry_id} routes)
# =============================================================================


@router.get("/export")
async def export_entries(
    export_format: Literal["json", "csv"] = Query(
        default="json", alias="format", description="Export format (json or csv)"
    ),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all journal entries (GDPR data portability)."""
    service = JournalService(db)
    entries, _ = await service.list_entries(user_id=user.id, limit=10000)

    if export_format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "id",
                "theme",
                "level",
                "title",
                "content",
                "mood",
                "status",
                "source",
                "personality_code",
                "char_count",
                "confidence",
                "evidence_count",
                "contradiction_count",
                "injection_count",
                "last_injected_at",
                "created_at",
                "updated_at",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    str(entry.id),
                    entry.theme,
                    entry.level,
                    entry.title,
                    entry.content,
                    entry.mood,
                    entry.status,
                    entry.source,
                    entry.personality_code,
                    entry.char_count,
                    entry.confidence,
                    entry.evidence_count,
                    entry.contradiction_count,
                    entry.injection_count,
                    entry.last_injected_at.isoformat() if entry.last_injected_at else "",
                    entry.created_at.isoformat(),
                    entry.updated_at.isoformat() if entry.updated_at else "",
                ]
            )
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=journal_entries.csv"},
        )

    # JSON format — also includes the compiled portrait for full GDPR portability
    data = {
        "entries": [
            {
                "id": str(entry.id),
                "theme": entry.theme,
                "level": entry.level,
                "title": entry.title,
                "content": entry.content,
                "mood": entry.mood,
                "status": entry.status,
                "source": entry.source,
                "personality_code": entry.personality_code,
                "char_count": entry.char_count,
                "confidence": entry.confidence,
                "evidence_count": entry.evidence_count,
                "contradiction_count": entry.contradiction_count,
                "injection_count": entry.injection_count,
                "last_injected_at": (
                    entry.last_injected_at.isoformat() if entry.last_injected_at else None
                ),
                "created_at": entry.created_at.isoformat(),
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
            for entry in entries
        ],
        "portrait": {
            "full": getattr(user, "journal_portrait_full", None),
            "brief": getattr(user, "journal_portrait_brief", None),
            "compiled_at": (
                _portrait_compiled_at.isoformat()
                if (_portrait_compiled_at := getattr(user, "journal_portrait_compiled_at", None))
                else None
            ),
        },
    }
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=journal_entries.json"},
    )


# =============================================================================
# Entry Endpoints (dynamic paths with /{entry_id})
# =============================================================================


@router.get("", response_model=JournalEntryListResponse)
async def list_entries(
    theme: str | None = Query(None, description="Filter by theme code"),
    entry_status: str | None = Query(
        None, alias="status", description="Filter by status (active/archived)"
    ),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryListResponse:
    """List journal entries with optional filters and size info."""
    service = JournalService(db)

    entries, total = await service.list_entries(
        user_id=user.id,
        theme=theme,
        status=entry_status,
        limit=limit,
        offset=offset,
    )

    theme_counts = await service.get_theme_counts(user.id)
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    size_info = await service.get_size_info(user.id, max_total_chars)

    return JournalEntryListResponse(
        entries=[_entry_to_response(e) for e in entries],
        total=total,
        by_theme=_build_theme_counts(theme_counts, user_id=user.id),
        total_chars=size_info.total_chars,
        max_total_chars=size_info.max_total_chars,
        usage_pct=size_info.usage_pct,
    )


@router.post("", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_entry(
    data: JournalEntryCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Create a new journal entry manually."""
    service = JournalService(db)

    entry = await service.create_entry(
        user_id=user.id,
        theme=data.theme.value,
        title=data.title,
        content=data.content,
        mood=data.mood.value,
        source=JournalEntrySource.MANUAL.value,
        search_hints=data.search_hints,
    )

    await db.commit()
    return _entry_to_response(entry)


@router.patch("/{entry_id}", response_model=JournalEntryResponse)
async def update_entry(
    entry_id: UUID,
    data: JournalEntryUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalEntryResponse:
    """Update a journal entry (title, content, mood).

    Raises:
        ResourceNotFoundError: If entry does not exist or belongs to another user.
    """
    service = JournalService(db)

    entry = await service.get_entry_for_user(entry_id, user.id)
    if not entry:
        raise ResourceNotFoundError(resource_type="journal_entry", resource_id=entry_id)

    updated = await service.update_entry(
        entry=entry,
        title=data.title,
        content=data.content,
        mood=data.mood.value if data.mood else None,
        search_hints=data.search_hints,
        confidence=data.confidence.value if data.confidence else None,
        level=data.level.value if data.level else None,
    )

    await db.commit()
    return _entry_to_response(updated)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    entry_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a journal entry.

    Raises:
        ResourceNotFoundError: If entry does not exist or belongs to another user.
    """
    service = JournalService(db)

    entry = await service.get_entry_for_user(entry_id, user.id)
    if not entry:
        raise ResourceNotFoundError(resource_type="journal_entry", resource_id=entry_id)

    await service.delete_entry(entry)
    await db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_entries(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete all journal entries for the current user (GDPR)."""
    service = JournalService(db)
    await service.delete_all_for_user(user.id)
    await db.commit()


@router.post("/consolidate", response_model=JournalConsolidationResponse)
async def consolidate_now(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalConsolidationResponse:
    """Trigger a synchronous manual consolidation of the user's journal.

    Same logic as the periodic scheduler — dedup, reformat, level promotions,
    confidence adjustments — but bypasses the cooldown so the user can see
    the effect immediately. Respects per-user usage limits (returns 429 if
    the user has exceeded their LLM quota).

    The call is synchronous and may take 5-15 seconds depending on the size
    of the journal and the LLM load. The frontend should display a loader.

    Raises:
        UsageLimitExceededError (429): Per-user LLM quota exceeded.
    """
    import time

    from src.core.exceptions import raise_usage_limit_exceeded
    from src.domains.journals.consolidation_service import consolidate_journals_for_user
    from src.domains.usage_limits.service import UsageLimitService

    # Pre-check usage limit (consistent with scheduler behaviour).
    if await UsageLimitService.is_user_blocked_for_llm(user.id, layer="journal_consolidation"):
        raise_usage_limit_exceeded(
            limit_name="journal_consolidation",
            reason="LLM quota exceeded — try again later.",
        )

    # Resolve personality (best-effort, defaults to None).
    personality_instruction: str | None = None
    personality_code: str | None = None
    if user.personality_id:
        try:
            from src.domains.personalities.service import PersonalityService

            personality = await PersonalityService(db).get_by_id(user.personality_id)
            if personality:
                personality_instruction = personality.prompt_instruction
                personality_code = personality.code
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "journal_consolidate_now_personality_load_failed",
                user_id=str(user.id),
                error=str(exc),
            )

    user_language = getattr(user, "language", settings.default_language)
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    max_entry_chars = getattr(user, "journal_max_entry_chars", settings.journal_max_entry_chars)
    consolidation_with_history = bool(getattr(user, "journal_consolidation_with_history", False))

    started = time.monotonic()
    actions_applied = await consolidate_journals_for_user(
        user_id=user.id,
        personality_instruction=personality_instruction,
        personality_code=personality_code,
        user_language=user_language,
        consolidation_with_history=consolidation_with_history,
        max_total_chars=max_total_chars,
        max_entry_chars=max_entry_chars,
        last_consolidated_at=user.journal_last_consolidated_at,
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    logger.info(
        "journal_consolidate_now_completed",
        user_id=str(user.id),
        actions_applied=actions_applied,
        duration_ms=duration_ms,
    )

    return JournalConsolidationResponse(
        actions_applied=actions_applied,
        duration_ms=duration_ms,
    )


# =============================================================================
# Portrait endpoints (ADR-079, commit 3)
# =============================================================================


@router.get("/portrait", response_model=JournalPortraitResponse)
async def get_portrait(
    user: User = Depends(get_current_active_session),
) -> JournalPortraitResponse:
    """Read the compiled user-model portrait (full + brief + compiled_at).

    The portrait is produced by the consolidation. This endpoint exposes
    it read-only — the user cannot edit the portrait directly. Three levers
    are available instead (see ADR-079):
    1. Edit/delete L3 source entries via the standard CRUD endpoints
    2. POST a feedback signal via /journals/portrait/feedback (lever 2)
    3. Trigger a full consolidation via /journals/consolidate (lever 3)
    """
    return JournalPortraitResponse(
        full=getattr(user, "journal_portrait_full", None),
        brief=getattr(user, "journal_portrait_brief", None),
        compiled_at=getattr(user, "journal_portrait_compiled_at", None),
    )


@router.post("/portrait/feedback", response_model=JournalConsolidationResponse)
async def portrait_feedback(
    data: JournalPortraitFeedbackRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalConsolidationResponse:
    """Lever 2 — user signals that the portrait is wrong / outdated / unfair.

    The signal is persisted as a journal entry (level=L0,
    source=user_correction) so the consolidation LLM picks it up in priority,
    then a synchronous consolidation runs that adjusts the L3 sources and
    recompiles the portrait. Same usage limit and personality resolution
    pattern as ``POST /journals/consolidate``.

    Raises:
        UsageLimitExceededError (429): Per-user LLM quota exceeded.
    """
    import time

    from src.core.exceptions import raise_usage_limit_exceeded
    from src.domains.journals.consolidation_service import consolidate_journals_for_user
    from src.domains.usage_limits.service import UsageLimitService

    if await UsageLimitService.is_user_blocked_for_llm(user.id, layer="journal_consolidation"):
        raise_usage_limit_exceeded(
            limit_name="journal_consolidation",
            reason="LLM quota exceeded — try again later.",
        )

    # 1. Persist the user's correction as a fresh L0 entry the consolidation
    #    will see in its working set. Phrased so the LLM understands it is
    #    feedback ON the portrait, not an observation about the user.
    correction_title = "User feedback on portrait"
    correction_body = data.comment.strip()
    if data.highlighted_section:
        correction_body = (
            f"User highlighted: «{data.highlighted_section.strip()}»\n"
            f"User feedback: {correction_body}"
        )
    # Theme by subject (see JOURNAL_PORTRAIT_FEEDBACK_THEME): portrait feedback
    # corrects the model of the USER, so it is a `user_observations` feedstock.
    service = JournalService(db)
    await service.create_entry(
        user_id=user.id,
        theme=JOURNAL_PORTRAIT_FEEDBACK_THEME,
        title=correction_title,
        content=correction_body[: settings.journal_max_entry_chars],
        source="user_correction",
        max_entry_chars=settings.journal_max_entry_chars,
        confidence="high",
        level="L0",
    )
    await db.commit()

    # 2. Resolve personality (best-effort).
    personality_instruction: str | None = None
    personality_code: str | None = None
    if user.personality_id:
        try:
            from src.domains.personalities.service import PersonalityService

            personality = await PersonalityService(db).get_by_id(user.personality_id)
            if personality:
                personality_instruction = personality.prompt_instruction
                personality_code = personality.code
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "journal_portrait_feedback_personality_load_failed",
                user_id=str(user.id),
                error=str(exc),
            )

    # 3. Run a synchronous consolidation. Like the manual /consolidate, it
    #    respects the user's `journal_consolidation_with_history` setting.
    user_language = getattr(user, "language", settings.default_language)
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    max_entry_chars = getattr(user, "journal_max_entry_chars", settings.journal_max_entry_chars)
    consolidation_with_history = bool(getattr(user, "journal_consolidation_with_history", False))

    started = time.monotonic()
    actions_applied = await consolidate_journals_for_user(
        user_id=user.id,
        personality_instruction=personality_instruction,
        personality_code=personality_code,
        user_language=user_language,
        consolidation_with_history=consolidation_with_history,
        max_total_chars=max_total_chars,
        max_entry_chars=max_entry_chars,
        last_consolidated_at=user.journal_last_consolidated_at,
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    with suppress(Exception):
        from src.infrastructure.observability.metrics_journals import (
            journal_portrait_feedback_total,
        )

        journal_portrait_feedback_total.labels(outcome="success").inc()

    logger.info(
        "journal_portrait_feedback_processed",
        user_id=str(user.id),
        actions_applied=actions_applied,
        duration_ms=duration_ms,
    )

    return JournalConsolidationResponse(
        actions_applied=actions_applied,
        duration_ms=duration_ms,
    )
