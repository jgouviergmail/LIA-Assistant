"""
Google API usage tracking service for non-chat contexts.

Provides direct database recording for API calls made outside of chat context
(e.g., photo proxy, home location geocoding).

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import UserStatistics
from src.domains.chat.repository import UserStatisticsRepository
from src.domains.google_api.pricing_service import GoogleApiPricingService
from src.domains.google_api.repository import GoogleApiUsageRepository
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class GoogleApiUsageService:
    """
    Track Google API usage outside of chat context.

    Used for:
    - Photo proxy endpoint (places photos)
    - Home location geocoding (user settings)

    These calls don't have a TrackingContext, so they're recorded directly.
    """

    @classmethod
    async def record_api_call(
        cls,
        db: AsyncSession,
        user_id: UUID,
        api_name: str,
        endpoint: str,
        run_id: str | None = None,
    ) -> None:
        """
        Record a Google API call directly to database.

        This method is for non-chat API calls that don't have a TrackingContext.
        It creates a usage log and updates user statistics.

        Note: Does NOT commit - caller must commit the transaction.

        Args:
            db: Database session
            user_id: User who triggered the API call
            api_name: API identifier (places, routes, geocoding, static_maps)
            endpoint: Endpoint called
            run_id: Optional run_id (defaults to synthetic "direct_" + UUID)
        """
        # Get cost from pricing cache
        cost_usd, cost_eur, usd_to_eur_rate = GoogleApiPricingService.get_cost_per_request(
            api_name, endpoint
        )

        # Generate synthetic run_id for non-chat calls
        if run_id is None:
            run_id = f"direct_{uuid4().hex[:12]}"

        # Create usage log
        usage_repo = GoogleApiUsageRepository(db)
        await usage_repo.create_log(
            user_id=user_id,
            run_id=run_id,
            api_name=api_name,
            endpoint=endpoint,
            cost_usd=float(cost_usd),
            cost_eur=float(cost_eur),
            usd_to_eur_rate=float(usd_to_eur_rate),
            cached=False,
        )

        # Update user statistics
        await cls._increment_user_statistics(
            db=db,
            user_id=user_id,
            requests=1,
            cost_eur=cost_eur,
        )

        logger.info(
            "google_api_direct_call_recorded",
            user_id=str(user_id),
            api_name=api_name,
            endpoint=endpoint,
            cost_eur=float(cost_eur),
            run_id=run_id,
        )

    @classmethod
    async def _increment_user_statistics(
        cls,
        db: AsyncSession,
        user_id: UUID,
        requests: int,
        cost_eur: Decimal,
    ) -> None:
        """
        Increment Google API statistics for a user.

        Updates both lifetime totals and current cycle counters.

        Args:
            db: Database session
            user_id: User UUID
            requests: Number of requests to add
            cost_eur: Cost in EUR to add
        """
        from sqlalchemy import update

        # Try to update existing statistics
        stmt = (
            update(UserStatistics)
            .where(UserStatistics.user_id == user_id)
            .values(
                total_google_api_requests=UserStatistics.total_google_api_requests + requests,
                total_google_api_cost_eur=UserStatistics.total_google_api_cost_eur + cost_eur,
                cycle_google_api_requests=UserStatistics.cycle_google_api_requests + requests,
                cycle_google_api_cost_eur=UserStatistics.cycle_google_api_cost_eur + cost_eur,
            )
        )

        result = await db.execute(stmt)

        if result.rowcount == 0:  # type: ignore[attr-defined]
            # No existing statistics - need to create new record
            # This is unusual (should exist after first chat), but handle it
            stats_repo = UserStatisticsRepository(db)
            existing = await stats_repo.get_by_user_id(user_id)

            if existing is None:
                logger.warning(
                    "google_api_stats_no_user_statistics",
                    user_id=str(user_id),
                    message="User has no statistics record - Google API call not tracked",
                )
                # Skip tracking - user statistics don't exist yet
                # This can happen if user never sent a chat message
                return

        logger.debug(
            "google_api_user_statistics_incremented",
            user_id=str(user_id),
            requests=requests,
            cost_eur=float(cost_eur),
        )
