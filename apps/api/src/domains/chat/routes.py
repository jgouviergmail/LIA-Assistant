"""
API routes for chat domain - user statistics and token usage.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.chat.schemas import UserStatisticsResponse
from src.domains.chat.service import StatisticsService

router = APIRouter(prefix="/chat", tags=["chat"])


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
