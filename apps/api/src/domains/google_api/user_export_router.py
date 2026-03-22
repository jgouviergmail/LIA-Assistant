"""
User-facing consumption export endpoints.

Allows authenticated users to export their own consumption data only.
Security: user_id is always forced to current_user.id — no user_id parameter
is exposed, preventing any attempt to export another user's data.
"""

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.models import User
from src.domains.google_api.export_service import (
    export_consumption_summary_csv,
    export_google_api_usage_csv,
    export_token_usage_csv,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/usage/export",
    tags=["usage", "export"],
)


@router.get("/token-usage")
async def user_export_token_usage(
    start_date: str | None = None,
    end_date: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Export the current user's LLM token usage logs as CSV.

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)

    Returns CSV file with the authenticated user's token usage data only.
    """
    response, rows_count = await export_token_usage_csv(
        db, start_date, end_date, user_id=current_user.id
    )

    logger.info(
        "user_token_usage_exported",
        rows_count=rows_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(current_user.id),
    )

    return response


@router.get("/google-api-usage")
async def user_export_google_api_usage(
    start_date: str | None = None,
    end_date: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Export the current user's Google API usage logs as CSV.

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)

    Returns CSV file with the authenticated user's Google API usage data only.
    """
    response, rows_count = await export_google_api_usage_csv(
        db, start_date, end_date, user_id=current_user.id
    )

    logger.info(
        "user_google_api_usage_exported",
        rows_count=rows_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(current_user.id),
    )

    return response


@router.get("/consumption-summary")
async def user_export_consumption_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_session),
) -> StreamingResponse:
    """
    Export the current user's aggregated consumption summary as CSV.

    **Query Parameters**:
    - `start_date`: Filter logs from this date (ISO format: YYYY-MM-DD)
    - `end_date`: Filter logs until this date (ISO format: YYYY-MM-DD)

    Returns CSV file with the authenticated user's consumption totals only.
    """
    response, users_count = await export_consumption_summary_csv(
        db, start_date, end_date, user_id=current_user.id
    )

    logger.info(
        "user_consumption_summary_exported",
        users_count=users_count,
        start_date=start_date,
        end_date=end_date,
        user_id=str(current_user.id),
    )

    return response
