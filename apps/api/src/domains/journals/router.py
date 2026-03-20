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
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import (
    JOURNAL_CONSOLIDATION_ENABLED_DEFAULT,
    JOURNAL_CONSOLIDATION_WITH_HISTORY_DEFAULT,
    JOURNALS_ENABLED_DEFAULT,
)
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.journals.models import JournalEntry, JournalEntrySource, JournalTheme
from src.domains.journals.schemas import (
    JournalEntryCreate,
    JournalEntryListResponse,
    JournalEntryResponse,
    JournalEntryUpdate,
    JournalSettingsResponse,
    JournalSettingsUpdate,
    JournalThemeInfo,
    JournalThemesResponse,
    ThemeCount,
)
from src.domains.journals.service import JournalService
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
        journals_enabled=getattr(user, "journals_enabled", JOURNALS_ENABLED_DEFAULT),
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
                "title",
                "content",
                "mood",
                "status",
                "source",
                "personality_code",
                "char_count",
                "created_at",
                "updated_at",
            ]
        )
        for entry in entries:
            writer.writerow(
                [
                    str(entry.id),
                    entry.theme,
                    entry.title,
                    entry.content,
                    entry.mood,
                    entry.status,
                    entry.source,
                    entry.personality_code,
                    entry.char_count,
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

    # JSON format
    data = [
        {
            "id": str(entry.id),
            "theme": entry.theme,
            "title": entry.title,
            "content": entry.content,
            "mood": entry.mood,
            "status": entry.status,
            "source": entry.source,
            "personality_code": entry.personality_code,
            "char_count": entry.char_count,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
        }
        for entry in entries
    ]
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
        by_theme=[ThemeCount(theme=JournalTheme(t), count=c) for t, c in theme_counts.items()],
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
