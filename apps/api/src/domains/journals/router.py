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

from contextlib import suppress
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError
from src.core.i18n import normalize_language
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.journals.creation_commands import JournalCreationKind, create_managed_journal_entry
from src.domains.journals.management_export import export_managed_journals
from src.domains.journals.management_projection import (
    available_journal_themes,
)
from src.domains.journals.management_projection import (
    build_journal_settings as _build_settings_response,
)
from src.domains.journals.management_projection import (
    build_journal_theme_counts as _build_theme_counts,
)
from src.domains.journals.models import JournalEntry
from src.domains.journals.portrait_feedback_configuration import portrait_feedback_entry
from src.domains.journals.portrait_read import read_managed_portrait
from src.domains.journals.preference_commands import update_journal_preferences
from src.domains.journals.removal_commands import remove_journal_entries
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
    JournalThemesResponse,
)
from src.domains.journals.service import JournalService
from src.domains.journals.update_commands import update_managed_journal_entry
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/journals",
    tags=["Journals"],
    # The deployment ceiling already decides whether this router is
    # mounted at all; this is the operator's switch inside it (B7).
    dependencies=capability_dependencies(PlatformCapability.JOURNALS),
)


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


# =============================================================================
# Themes Endpoint (static path — must be before /{entry_id} routes)
# =============================================================================


@router.get("/themes", response_model=JournalThemesResponse)
async def list_themes(
    user: User = Depends(get_current_active_session),
) -> JournalThemesResponse:
    """List available journal themes with labels."""
    return available_journal_themes()


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
    return await update_journal_preferences(db, user.id, data)


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
    return await export_managed_journals(db, user.id, export_format)


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
    return await create_managed_journal_entry(db, user.id, data)


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
    return await update_managed_journal_entry(db, user.id, entry_id, data)


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
    await remove_journal_entries(db, user.id, entry_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_entries(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete all journal entries for the current user (GDPR)."""
    await remove_journal_entries(db, user.id, None)


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
    from src.domains.journals.consolidation_lifecycle import ConsolidationAttempt
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

    user_language = normalize_language(getattr(user, "language", None))
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    max_entry_chars = getattr(user, "journal_max_entry_chars", settings.journal_max_entry_chars)
    consolidation_with_history = bool(getattr(user, "journal_consolidation_with_history", False))

    attempt = ConsolidationAttempt()
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
        manual=True,
        attempt=attempt,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    await db.refresh(user)

    logger.info(
        "journal_consolidate_now_completed",
        user_id=str(user.id),
        actions_applied=actions_applied,
        duration_ms=duration_ms,
    )

    return JournalConsolidationResponse(
        actions_applied=actions_applied,
        duration_ms=duration_ms,
        status=attempt.status,
    )


# =============================================================================
# Portrait endpoints (ADR-079, commit 3)
# =============================================================================


@router.get("/portrait", response_model=JournalPortraitResponse)
async def get_portrait(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> JournalPortraitResponse:
    """Read the compiled user-model portrait (full + brief + compiled_at).

    The portrait is produced by the consolidation. This endpoint exposes
    it read-only — the user cannot edit the portrait directly. Three levers
    are available instead (see ADR-079):
    1. Edit/delete L3 source entries via the standard CRUD endpoints
    2. POST a feedback signal via /journals/portrait/feedback (lever 2)
    3. Trigger a full consolidation via /journals/consolidate (lever 3)
    """
    return await read_managed_portrait(db, user)


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
    from src.domains.journals.consolidation_lifecycle import ConsolidationAttempt
    from src.domains.journals.consolidation_service import consolidate_journals_for_user
    from src.domains.usage_limits.service import UsageLimitService

    if await UsageLimitService.is_user_blocked_for_llm(user.id, layer="journal_consolidation"):
        raise_usage_limit_exceeded(
            limit_name="journal_consolidation",
            reason="LLM quota exceeded — try again later.",
        )

    # The source command preserves complete correction text and prepares embeddings outside locks.
    await create_managed_journal_entry(
        db, user.id, portrait_feedback_entry(data), kind=JournalCreationKind.PORTRAIT_CORRECTION
    )

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
    user_language = normalize_language(getattr(user, "language", None))
    max_total_chars = getattr(
        user, "journal_max_total_chars", settings.journal_default_max_total_chars
    )
    max_entry_chars = getattr(user, "journal_max_entry_chars", settings.journal_max_entry_chars)
    consolidation_with_history = bool(getattr(user, "journal_consolidation_with_history", False))

    attempt = ConsolidationAttempt()
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
        manual=True,
        attempt=attempt,
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    await db.refresh(user)

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
        status=attempt.status,
    )

    return JournalConsolidationResponse(
        actions_applied=actions_applied,
        duration_ms=duration_ms,
        status=attempt.status,
    )


@router.get("/{entry_id}/provenance", response_model=ProvenanceResponse)
async def get_entry_provenance(
    entry_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ProvenanceResponse:
    """Why LIA thinks this — the signals behind one entry.

    Bounded references, resolved LIVE. A reference whose conversation the
    reader has since deleted comes back as a TOMBSTONE: dated, sourceless and
    textless. Nothing here reproduces content the user removed elsewhere; that
    would turn their deletion into a copy.

    Args:
        entry_id: The entry being questioned.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The references, newest first, and how many are kept.

    Raises:
        ResourceNotFoundError: Unknown entry, or one belonging to another
            account — the two answer identically, so the route cannot be used
            to probe for someone else's journal.
    """
    entry = await JournalService(db).get_entry_for_user(entry_id, user.id)
    if not entry:
        raise ResourceNotFoundError(resource_type="journal_entry", resource_id=entry_id)

    references = await ProvenanceRepository(db).resolve_for(
        user_id=user.id, journal_entry_id=entry_id
    )
    return ProvenanceResponse.from_references(references)
