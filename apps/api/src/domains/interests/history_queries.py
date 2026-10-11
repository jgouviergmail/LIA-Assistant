"""The source audit count has one query authority for the UI and native snapshots."""

from uuid import UUID

from sqlalchemy import Select, func, select

from src.domains.interests.models import InterestNotification


def interest_history_count_statement(user_id: UUID) -> Select[tuple[int]]:
    return (
        select(func.count())
        .select_from(InterestNotification)
        .where(InterestNotification.user_id == user_id)
    )
