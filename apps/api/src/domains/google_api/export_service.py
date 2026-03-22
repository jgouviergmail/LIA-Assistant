"""
Shared export query logic for consumption data.

Provides reusable query builders for token usage, Google API usage,
and consumption summary exports. Used by both admin and user export endpoints
to avoid code duplication.
"""

import uuid
from datetime import datetime

from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import raise_invalid_input
from src.core.export_utils import create_csv_response
from src.domains.auth.models import User as UserModel
from src.domains.chat.models import TokenUsageLog
from src.domains.google_api.models import GoogleApiUsageLog


def _parse_date_range(
    start_date: str | None,
    end_date: str | None,
) -> tuple[datetime | None, datetime | None]:
    """
    Parse and validate date range strings.

    Args:
        start_date: Start date in ISO YYYY-MM-DD format, or None.
        end_date: End date in ISO YYYY-MM-DD format, or None.

    Returns:
        Tuple of (start_datetime, end_datetime) with end adjusted to end of day.

    Raises:
        HTTPException: If date format is invalid.
    """
    start_dt = None
    end_dt = None

    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date)
        except ValueError:
            raise_invalid_input("Invalid start_date format. Use YYYY-MM-DD.")

    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date)
            # Include the entire end day
            end_dt = end_dt.replace(hour=23, minute=59, second=59)
        except ValueError:
            raise_invalid_input("Invalid end_date format. Use YYYY-MM-DD.")

    return start_dt, end_dt


async def export_token_usage_csv(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[StreamingResponse, int]:
    """
    Build and execute token usage export query, return CSV response.

    Args:
        db: Async database session.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        user_id: Optional user ID filter. When set, only this user's data is exported.

    Returns:
        Tuple of (StreamingResponse with CSV, row count).
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    stmt = select(
        TokenUsageLog,
        UserModel.email,
    ).join(UserModel, TokenUsageLog.user_id == UserModel.id)

    if start_dt:
        stmt = stmt.where(TokenUsageLog.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(TokenUsageLog.created_at <= end_dt)
    if user_id:
        stmt = stmt.where(TokenUsageLog.user_id == user_id)

    stmt = stmt.order_by(TokenUsageLog.created_at.desc())

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            "date": row[0].created_at.isoformat(),
            "user_email": row[1],
            "run_id": row[0].run_id,
            "node_name": row[0].node_name,
            "model_name": row[0].model_name,
            "prompt_tokens": row[0].prompt_tokens,
            "completion_tokens": row[0].completion_tokens,
            "cached_tokens": row[0].cached_tokens,
            "cost_usd": float(row[0].cost_usd),
            "cost_eur": float(row[0].cost_eur),
        }
        for row in rows
    ]

    return create_csv_response(data, "token_usage"), len(data)


async def export_google_api_usage_csv(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[StreamingResponse, int]:
    """
    Build and execute Google API usage export query, return CSV response.

    Args:
        db: Async database session.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        user_id: Optional user ID filter. When set, only this user's data is exported.

    Returns:
        Tuple of (StreamingResponse with CSV, row count).
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    stmt = select(
        GoogleApiUsageLog,
        UserModel.email,
    ).join(UserModel, GoogleApiUsageLog.user_id == UserModel.id)

    if start_dt:
        stmt = stmt.where(GoogleApiUsageLog.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(GoogleApiUsageLog.created_at <= end_dt)
    if user_id:
        stmt = stmt.where(GoogleApiUsageLog.user_id == user_id)

    stmt = stmt.order_by(GoogleApiUsageLog.created_at.desc())

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            "date": row[0].created_at.isoformat(),
            "user_email": row[1],
            "run_id": row[0].run_id,
            "api_name": row[0].api_name,
            "endpoint": row[0].endpoint,
            "request_count": row[0].request_count,
            "cost_usd": float(row[0].cost_usd),
            "cost_eur": float(row[0].cost_eur),
            "cached": row[0].cached,
        }
        for row in rows
    ]

    return create_csv_response(data, "google_api_usage"), len(data)


async def export_consumption_summary_csv(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[StreamingResponse, int]:
    """
    Build and execute consumption summary export query, return CSV response.

    Aggregates token usage and Google API usage per user.

    Args:
        db: Async database session.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        user_id: Optional user ID filter. When set, only this user's data is exported.

    Returns:
        Tuple of (StreamingResponse with CSV, row count).
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    # Query token usage aggregated by user
    token_stmt = select(
        TokenUsageLog.user_id,
        func.sum(TokenUsageLog.prompt_tokens).label("total_prompt_tokens"),
        func.sum(TokenUsageLog.completion_tokens).label("total_completion_tokens"),
        func.sum(TokenUsageLog.cached_tokens).label("total_cached_tokens"),
        func.sum(TokenUsageLog.cost_eur).label("total_llm_cost_eur"),
        func.count().label("total_llm_calls"),
    )

    if start_dt:
        token_stmt = token_stmt.where(TokenUsageLog.created_at >= start_dt)
    if end_dt:
        token_stmt = token_stmt.where(TokenUsageLog.created_at <= end_dt)
    if user_id:
        token_stmt = token_stmt.where(TokenUsageLog.user_id == user_id)

    token_stmt = token_stmt.group_by(TokenUsageLog.user_id)
    token_result = await db.execute(token_stmt)
    token_rows = {row[0]: row for row in token_result.all()}

    # Query Google API usage aggregated by user
    google_stmt = select(
        GoogleApiUsageLog.user_id,
        func.sum(GoogleApiUsageLog.request_count).label("total_google_requests"),
        func.sum(GoogleApiUsageLog.cost_eur).label("total_google_cost_eur"),
    )

    if start_dt:
        google_stmt = google_stmt.where(GoogleApiUsageLog.created_at >= start_dt)
    if end_dt:
        google_stmt = google_stmt.where(GoogleApiUsageLog.created_at <= end_dt)
    if user_id:
        google_stmt = google_stmt.where(GoogleApiUsageLog.user_id == user_id)

    google_stmt = google_stmt.group_by(GoogleApiUsageLog.user_id)
    google_result = await db.execute(google_stmt)
    google_rows = {row[0]: row for row in google_result.all()}

    # Get all unique user IDs
    all_user_ids = set(token_rows.keys()) | set(google_rows.keys())

    # Fetch user emails
    users_stmt = select(UserModel.id, UserModel.email).where(UserModel.id.in_(all_user_ids))
    users_result = await db.execute(users_stmt)
    user_emails = {row[0]: row[1] for row in users_result.all()}

    # Build combined data
    data = []
    for uid in all_user_ids:
        token_data = token_rows.get(uid)
        google_data = google_rows.get(uid)

        total_prompt_tokens = int(token_data[1] or 0) if token_data else 0
        total_completion_tokens = int(token_data[2] or 0) if token_data else 0
        total_cached_tokens = int(token_data[3] or 0) if token_data else 0
        total_llm_cost_eur = float(token_data[4] or 0) if token_data else 0.0
        total_llm_calls = int(token_data[5] or 0) if token_data else 0

        total_google_requests = int(google_data[1] or 0) if google_data else 0
        total_google_cost_eur = float(google_data[2] or 0) if google_data else 0.0

        total_cost_eur = total_llm_cost_eur + total_google_cost_eur

        data.append(
            {
                "user_email": user_emails.get(uid, "Unknown"),
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_cached_tokens": total_cached_tokens,
                "total_llm_calls": total_llm_calls,
                "total_llm_cost_eur": round(total_llm_cost_eur, 6),
                "total_google_requests": total_google_requests,
                "total_google_cost_eur": round(total_google_cost_eur, 6),
                "total_cost_eur": round(total_cost_eur, 6),
            }
        )

    # Sort by total cost descending
    data.sort(key=lambda x: x["total_cost_eur"], reverse=True)

    return create_csv_response(data, "consumption_summary"), len(data)
