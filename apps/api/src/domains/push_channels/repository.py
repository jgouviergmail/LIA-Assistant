"""Push channel repository (lot H, 2026-08)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.push_channels.models import WebhookChannel


class PushChannelRepository(BaseRepository[WebhookChannel]):
    """CRUD + lookups for the push channel registry."""

    def __init__(self, db: AsyncSession) -> None:
        """Bind the repository to a session.

        Args:
            db: Async database session.
        """
        super().__init__(db, WebhookChannel)

    async def get_by_channel_id(self, channel_id: str) -> WebhookChannel | None:
        """Resolve a notification's X-Goog-Channel-ID to its registry row."""
        result = await self.db.execute(
            select(WebhookChannel).where(WebhookChannel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

    async def get_by_provider_target(
        self, provider: str, watch_target: str
    ) -> WebhookChannel | None:
        """Resolve a (provider, target) pair — Gmail push resolves by mailbox."""
        result = await self.db.execute(
            select(WebhookChannel).where(
                WebhookChannel.provider == provider,
                WebhookChannel.watch_target == watch_target,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_user(
        self, user_id: UUID, provider: str, watch_target: str
    ) -> WebhookChannel | None:
        """The user's channel for one (provider, target) — unique by constraint."""
        result = await self.db.execute(
            select(WebhookChannel).where(
                WebhookChannel.user_id == user_id,
                WebhookChannel.provider == provider,
                WebhookChannel.watch_target == watch_target,
            )
        )
        return result.scalar_one_or_none()

    async def list_expiring(self, before: datetime) -> list[WebhookChannel]:
        """Channels whose expiry falls before ``before`` (renewal candidates)."""
        result = await self.db.execute(
            select(WebhookChannel)
            .where(WebhookChannel.expiration < before)
            .order_by(WebhookChannel.expiration)
        )
        return list(result.scalars().all())

    async def delete_channels_not_in(self, provider: str, active_user_ids: set[UUID]) -> int:
        """Delete one provider's channels whose owner is NOT in the active set.

        An empty active set deletes every channel of the provider — correct:
        it means no user holds the matching connector anymore. The Google-side
        watch (unreachable without the user's credentials) dies at its own
        expiry; deleting the row makes its interim notifications unknown, so
        they are ignored.

        Returns:
            Number of deleted rows (exact).
        """
        result = await self.db.execute(
            delete(WebhookChannel).where(
                WebhookChannel.provider == provider,
                WebhookChannel.user_id.not_in(active_user_ids),
            )
        )
        # CursorResult.rowcount is exact for a DELETE; the base Result type
        # simply does not declare it.
        return int(getattr(result, "rowcount", 0) or 0)
