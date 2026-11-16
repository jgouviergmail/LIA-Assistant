"""Reads and writes of ntfy subscriptions (ADR-391).

A delivery reads its targets in a short session and publishes after it closed (ADR-304), so the
targets leave this module DETACHED: plain values, their secrets decrypted for that one delivery.
Every status is written after every publication, in one statement per outcome — per chunk of
ids, since the driver binds at most 32 767 values in one statement.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import SQL_IN_CLAUSE_CHUNK
from src.core.repository import BaseRepository
from src.core.security.utils import decrypt_data
from src.domains.notifications.models import NtfySubscription
from src.domains.notifications.ntfy import NtfyContent, NtfyServerKind
from src.infrastructure.external.ntfy_client import NtfyOutcome

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NtfyTarget:
    """One subscription to publish to, detached from any session."""

    id: UUID
    user_id: UUID
    server_kind: NtfyServerKind
    server_url: str | None
    topic: str
    token: str | None
    content: NtfyContent


def target_of(row: NtfySubscription) -> NtfyTarget:
    """A subscription as a delivery uses it, its secrets in clear.

    Args:
        row: The stored subscription.

    Returns:
        The detached target.
    """
    return NtfyTarget(
        id=row.id,
        user_id=row.user_id,
        server_kind=NtfyServerKind(row.server_kind),
        server_url=row.server_url,
        topic=decrypt_data(row.topic_encrypted),
        token=decrypt_data(row.token_encrypted) if row.token_encrypted else None,
        content=NtfyContent(row.content),
    )


class NtfySubscriptionRepository(BaseRepository[NtfySubscription]):
    """Subscriptions of the accounts, by owner."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize the repository on a session."""
        super().__init__(db, NtfySubscription)

    async def list_for_user(self, user_id: UUID) -> list[NtfySubscription]:
        """Every subscription of an account, oldest first.

        Args:
            user_id: The account.

        Returns:
            Its subscriptions, ordered by creation then id.
        """
        rows = await self.db.scalars(
            select(NtfySubscription)
            .where(NtfySubscription.user_id == user_id)
            .order_by(NtfySubscription.created_at, NtfySubscription.id)
        )
        return list(rows)

    async def count_for_user(self, user_id: UUID) -> int:
        """How many subscriptions an account holds, active or not."""
        total = await self.db.scalar(
            select(func.count())
            .select_from(NtfySubscription)
            .where(NtfySubscription.user_id == user_id)
        )
        return int(total or 0)

    async def active_targets(self, user_ids: Sequence[UUID]) -> list[NtfyTarget]:
        """The active subscriptions of some accounts, as detached targets.

        One query per ``SQL_IN_CLAUSE_CHUNK`` accounts: a broadcast reads a whole language
        group, which can hold more accounts than the driver binds in one statement.

        Args:
            user_ids: The accounts to reach.

        Returns:
            The targets, chunk after chunk, each ordered by account then creation.
        """
        targets: list[NtfyTarget] = []
        for chunk in _chunks(user_ids):
            rows = await self.db.scalars(
                select(NtfySubscription)
                .where(NtfySubscription.user_id.in_(chunk), NtfySubscription.is_active.is_(True))
                .order_by(
                    NtfySubscription.user_id, NtfySubscription.created_at, NtfySubscription.id
                )
            )
            targets.extend(_readable(rows))
        return targets

    async def record_outcomes(
        self, outcomes: Sequence[tuple[UUID, NtfyOutcome]], *, at: datetime
    ) -> None:
        """Remember how each publication ended: accepted, or refused and why.

        A refusal never deactivates a subscription: doubt never deletes a way to reach someone.

        Args:
            outcomes: Each subscription's outcome.
            at: When the publications ended.
        """
        by_outcome: dict[NtfyOutcome, list[UUID]] = {}
        for subscription, outcome in outcomes:
            by_outcome.setdefault(outcome, []).append(subscription)
        for outcome, subscriptions in by_outcome.items():
            values = (
                {"last_sent_at": at, "last_error_code": None, "last_error_at": None}
                if outcome is NtfyOutcome.SENT
                else {"last_error_code": outcome.value, "last_error_at": at}
            )
            for chunk in _chunks(subscriptions):
                await self.db.execute(
                    update(NtfySubscription)
                    .where(NtfySubscription.id.in_(chunk))
                    .values(**values, updated_at=at)
                )


def _chunks(ids: Sequence[UUID]) -> Iterator[Sequence[UUID]]:
    """The ids, ``SQL_IN_CLAUSE_CHUNK`` at a time."""
    for start in range(0, len(ids), SQL_IN_CLAUSE_CHUNK):
        yield ids[start : start + SQL_IN_CLAUSE_CHUNK]


def _readable(rows: Iterable[NtfySubscription]) -> Iterator[NtfyTarget]:
    """Each row as a target; one whose secret no longer decrypts is said and left out."""
    for row in rows:
        try:
            yield target_of(row)
        except ValueError:
            # A secret that no longer decrypts (a rotated key): this one target is said and
            # left out, never the whole delivery.
            logger.warning("ntfy_subscription_unreadable", subscription_id=str(row.id))


__all__ = ["NtfySubscriptionRepository", "NtfyTarget", "target_of"]
