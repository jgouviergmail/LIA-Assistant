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
from src.domains.chat.models import TokenUsageLog
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.google_api.models import GoogleApiUsageLog
from src.domains.users.models import User as UserModel


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

    Aggregates token usage, Google API usage and remote-STT usage per user.

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

    # Query remote-STT usage aggregated by user (joined via Conversation.user_id)
    stt_stmt = (
        select(
            Conversation.user_id,
            func.sum(ConversationMessage.stt_audio_duration_seconds).label("total_stt_seconds"),
            func.sum(ConversationMessage.stt_cost_eur).label("total_stt_cost_eur"),
            func.count().label("total_stt_calls"),
        )
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .where(ConversationMessage.stt_provider.is_not(None))
    )

    if start_dt:
        stt_stmt = stt_stmt.where(ConversationMessage.created_at >= start_dt)
    if end_dt:
        stt_stmt = stt_stmt.where(ConversationMessage.created_at <= end_dt)
    if user_id:
        stt_stmt = stt_stmt.where(Conversation.user_id == user_id)

    stt_stmt = stt_stmt.group_by(Conversation.user_id)
    stt_result = await db.execute(stt_stmt)
    stt_rows = {row[0]: row for row in stt_result.all()}

    # Query paid-TTS usage aggregated by user (joined via Conversation.user_id).
    # Mirror of STT: assistant messages synthesised by Edge stay NULL and are
    # excluded; OpenAI / ElevenLabs rows count.
    tts_stmt = (
        select(
            Conversation.user_id,
            func.sum(ConversationMessage.tts_characters).label("total_tts_chars"),
            func.sum(ConversationMessage.tts_cost_eur).label("total_tts_cost_eur"),
            func.count().label("total_tts_calls"),
        )
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .where(ConversationMessage.tts_provider.is_not(None))
    )

    if start_dt:
        tts_stmt = tts_stmt.where(ConversationMessage.created_at >= start_dt)
    if end_dt:
        tts_stmt = tts_stmt.where(ConversationMessage.created_at <= end_dt)
    if user_id:
        tts_stmt = tts_stmt.where(Conversation.user_id == user_id)

    tts_stmt = tts_stmt.group_by(Conversation.user_id)
    tts_result = await db.execute(tts_stmt)
    tts_rows = {row[0]: row for row in tts_result.all()}

    # Get all unique user IDs
    all_user_ids = (
        set(token_rows.keys())
        | set(google_rows.keys())
        | set(stt_rows.keys())
        | set(tts_rows.keys())
    )

    # Fetch user emails
    users_stmt = select(UserModel.id, UserModel.email).where(UserModel.id.in_(all_user_ids))
    users_result = await db.execute(users_stmt)
    user_emails = {row[0]: row[1] for row in users_result.all()}

    # Build combined data
    data = []
    for uid in all_user_ids:
        token_data = token_rows.get(uid)
        google_data = google_rows.get(uid)
        stt_data = stt_rows.get(uid)

        total_prompt_tokens = int(token_data[1] or 0) if token_data else 0
        total_completion_tokens = int(token_data[2] or 0) if token_data else 0
        total_cached_tokens = int(token_data[3] or 0) if token_data else 0
        total_llm_cost_eur = float(token_data[4] or 0) if token_data else 0.0
        total_llm_calls = int(token_data[5] or 0) if token_data else 0

        total_google_requests = int(google_data[1] or 0) if google_data else 0
        total_google_cost_eur = float(google_data[2] or 0) if google_data else 0.0

        total_stt_seconds = float(stt_data[1] or 0) if stt_data else 0.0
        total_stt_cost_eur = float(stt_data[2] or 0) if stt_data else 0.0
        total_stt_calls = int(stt_data[3] or 0) if stt_data else 0

        tts_data = tts_rows.get(uid)
        total_tts_chars = int(tts_data[1] or 0) if tts_data else 0
        total_tts_cost_eur = float(tts_data[2] or 0) if tts_data else 0.0
        total_tts_calls = int(tts_data[3] or 0) if tts_data else 0

        total_cost_eur = (
            total_llm_cost_eur + total_google_cost_eur + total_stt_cost_eur + total_tts_cost_eur
        )

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
                "total_stt_calls": total_stt_calls,
                "total_stt_audio_seconds": round(total_stt_seconds, 2),
                "total_stt_cost_eur": round(total_stt_cost_eur, 6),
                "total_tts_calls": total_tts_calls,
                "total_tts_characters": total_tts_chars,
                "total_tts_cost_eur": round(total_tts_cost_eur, 6),
                "total_cost_eur": round(total_cost_eur, 6),
            }
        )

    # Sort by total cost descending
    data.sort(key=lambda x: x["total_cost_eur"], reverse=True)

    return create_csv_response(data, "consumption_summary"), len(data)


async def export_stt_usage_csv(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[StreamingResponse, int]:
    """
    Build and execute remote-STT usage export query, return CSV response.

    One row per user message produced by a remote STT provider (e.g.
    ElevenLabs Scribe). Local Sherpa transcriptions and assistant messages
    are excluded by the ``stt_provider IS NOT NULL`` filter.

    Args:
        db: Async database session.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        user_id: Optional user ID filter. When set, only this user's data is exported.

    Returns:
        Tuple of (StreamingResponse with CSV, row count).
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    stmt = (
        select(
            ConversationMessage,
            Conversation.user_id,
            UserModel.email,
        )
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .join(UserModel, Conversation.user_id == UserModel.id)
        .where(ConversationMessage.stt_provider.is_not(None))
    )

    if start_dt:
        stmt = stmt.where(ConversationMessage.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(ConversationMessage.created_at <= end_dt)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)

    stmt = stmt.order_by(ConversationMessage.created_at.desc())

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            "date": msg.created_at.isoformat(),
            "user_email": email,
            "conversation_id": str(msg.conversation_id),
            "message_id": str(msg.id),
            "stt_provider": msg.stt_provider,
            "audio_duration_seconds": (
                float(msg.stt_audio_duration_seconds)
                if msg.stt_audio_duration_seconds is not None
                else 0.0
            ),
            "cost_usd": float(msg.stt_cost_usd) if msg.stt_cost_usd is not None else 0.0,
            "cost_eur": float(msg.stt_cost_eur) if msg.stt_cost_eur is not None else 0.0,
        }
        for msg, _uid, email in rows
    ]

    return create_csv_response(data, "stt_usage"), len(data)


async def export_tts_usage_csv(
    db: AsyncSession,
    start_date: str | None = None,
    end_date: str | None = None,
    user_id: uuid.UUID | None = None,
) -> tuple[StreamingResponse, int]:
    """
    Build and execute paid-TTS usage export query, return CSV response.

    One row per assistant message synthesised by a paid TTS provider
    (OpenAI tts-1/-hd, ElevenLabs eleven_*). Edge synthesis is excluded by
    the ``tts_provider IS NOT NULL`` filter (Edge is free, never tracked).

    Mirrors :func:`export_stt_usage_csv` for symmetry — same shape, different
    columns adapted to the per-character billing axis of TTS.

    Args:
        db: Async database session.
        start_date: Optional start date filter (YYYY-MM-DD).
        end_date: Optional end date filter (YYYY-MM-DD).
        user_id: Optional user ID filter. When set, only this user's data is exported.

    Returns:
        Tuple of (StreamingResponse with CSV, row count).
    """
    start_dt, end_dt = _parse_date_range(start_date, end_date)

    stmt = (
        select(
            ConversationMessage,
            Conversation.user_id,
            UserModel.email,
        )
        .join(Conversation, ConversationMessage.conversation_id == Conversation.id)
        .join(UserModel, Conversation.user_id == UserModel.id)
        .where(ConversationMessage.tts_provider.is_not(None))
    )

    if start_dt:
        stmt = stmt.where(ConversationMessage.created_at >= start_dt)
    if end_dt:
        stmt = stmt.where(ConversationMessage.created_at <= end_dt)
    if user_id:
        stmt = stmt.where(Conversation.user_id == user_id)

    stmt = stmt.order_by(ConversationMessage.created_at.desc())

    result = await db.execute(stmt)
    rows = result.all()

    data = [
        {
            "date": msg.created_at.isoformat(),
            "user_email": email,
            "conversation_id": str(msg.conversation_id),
            "message_id": str(msg.id),
            "tts_provider": msg.tts_provider,
            "tts_model": msg.tts_model or "",
            "characters": int(msg.tts_characters or 0),
            "cost_usd": float(msg.tts_cost_usd) if msg.tts_cost_usd is not None else 0.0,
            "cost_eur": float(msg.tts_cost_eur) if msg.tts_cost_eur is not None else 0.0,
        }
        for msg, _uid, email in rows
    ]

    return create_csv_response(data, "tts_usage"), len(data)
