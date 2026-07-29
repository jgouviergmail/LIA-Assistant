"""
API routes for chat domain - user statistics, token usage, slash shortcuts.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.chat.schemas import UserStatisticsResponse
from src.domains.chat.service import StatisticsService
from src.domains.chat.shortcuts import (
    ChatShortcutsPayload,
    ChatShortcutsResponse,
    sanitize_chat_shortcuts,
)
from src.domains.users.models import User

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "/shortcuts",
    response_model=ChatShortcutsResponse,
    summary="Get the user's slash shortcuts",
)
async def get_chat_shortcuts(
    current_user: User = Depends(get_current_active_session),
) -> ChatShortcutsResponse:
    """Sanitized view of the stored shortcuts (SLASH admin lot).

    NULL column → empty list; malformed stored entries are dropped, never a
    500 on the chat page.
    """
    sanitized = sanitize_chat_shortcuts(current_user.chat_shortcuts)
    return ChatShortcutsResponse(
        shortcuts=sanitized.shortcuts,
        max_count=settings.chat_shortcuts_max_count,
    )


@router.put(
    "/shortcuts",
    response_model=ChatShortcutsResponse,
    summary="Replace the user's slash shortcuts",
)
async def put_chat_shortcuts(
    payload: ChatShortcutsPayload,
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ChatShortcutsResponse:
    """Full replace of the shortcut list (SLASH admin lot).

    Shape validation is strict (bad slug, blank text, duplicates → 422); the
    COUNT cap reads the runtime setting so the schema stays static. The write
    is a plain NEW-list assignment — the JSONB new-dict rule.
    """
    if len(payload.shortcuts) > settings.chat_shortcuts_max_count:
        raise_invalid_input(
            f"Too many shortcuts (max {settings.chat_shortcuts_max_count})",
            max_count=settings.chat_shortcuts_max_count,
        )
    current_user.chat_shortcuts = [
        {"id": shortcut.id, "text": shortcut.text} for shortcut in payload.shortcuts
    ]
    db.add(current_user)
    await db.commit()
    sanitized = sanitize_chat_shortcuts(current_user.chat_shortcuts)
    return ChatShortcutsResponse(
        shortcuts=sanitized.shortcuts,
        max_count=settings.chat_shortcuts_max_count,
    )


@router.get("/users/me/statistics", response_model=UserStatisticsResponse)
async def get_user_statistics(
    current_user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> UserStatisticsResponse:
    """
    Get current user's token usage and message statistics.

    Returns both lifetime and current billing cycle metrics:
    - Token consumption (IN/OUT/CACHE)
    - Cost in EUR
    - Message count

    Billing cycle is monthly, aligned with user signup date.

    Args:
        current_user: Currently authenticated user
        db: Database session

    Returns:
        UserStatisticsResponse: User statistics
    """
    return await StatisticsService.get_user_statistics(current_user.id, db)
