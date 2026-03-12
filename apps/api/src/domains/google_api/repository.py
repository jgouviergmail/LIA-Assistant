"""
Repository for Google API tracking database operations.

Provides optimized queries for:
- Pricing configuration retrieval
- Usage log creation and queries

Author: Claude Code (Opus 4.5)
Date: 2026-02-04
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.google_api.models import GoogleApiPricing, GoogleApiUsageLog
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class GoogleApiPricingRepository:
    """
    Repository for GoogleApiPricing database operations.

    Provides methods to:
    - Get active pricing entries for cache loading
    - Get pricing for specific endpoints
    """

    def __init__(self, db: AsyncSession):
        """Initialize repository with database session."""
        self.db = db

    async def get_active_pricing(self) -> list[GoogleApiPricing]:
        """
        Get all active pricing entries.

        Used at startup to populate the pricing cache.

        Returns:
            List of active GoogleApiPricing entries.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await self.db.execute(
                select(GoogleApiPricing).where(GoogleApiPricing.is_active == True)  # noqa: E712
            )
            entries = list(result.scalars().all())

            logger.debug(
                "google_api_pricing_fetched",
                count=len(entries),
            )

            return entries

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_active_pricing_failed",
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def get_pricing_by_endpoint(
        self,
        api_name: str,
        endpoint: str,
    ) -> GoogleApiPricing | None:
        """
        Get pricing for a specific endpoint.

        Args:
            api_name: API identifier (places, routes, geocoding, static_maps)
            endpoint: Endpoint path

        Returns:
            GoogleApiPricing if found, None otherwise.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await self.db.execute(
                select(GoogleApiPricing).where(
                    GoogleApiPricing.api_name == api_name,
                    GoogleApiPricing.endpoint == endpoint,
                    GoogleApiPricing.is_active == True,  # noqa: E712
                )
            )
            return result.scalar_one_or_none()

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_pricing_by_endpoint_failed",
                api_name=api_name,
                endpoint=endpoint,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise


class GoogleApiUsageRepository:
    """
    Repository for GoogleApiUsageLog database operations.

    Provides methods to:
    - Bulk create usage logs
    - Query logs by run_id
    """

    def __init__(self, db: AsyncSession):
        """Initialize repository with database session."""
        self.db = db

    async def bulk_create_logs(self, logs_data: list[dict]) -> None:
        """
        Bulk insert usage logs.

        Optimized for batch insertion without returning created objects.

        Args:
            logs_data: List of log dictionaries with keys:
                - user_id, run_id, api_name, endpoint
                - cost_usd, cost_eur, usd_to_eur_rate
                - cached (optional, defaults to False)

        Raises:
            SQLAlchemyError: On database error.
        """
        if not logs_data:
            return

        try:
            stmt = pg_insert(GoogleApiUsageLog).values(logs_data)
            await self.db.execute(stmt)

            logger.debug(
                "google_api_usage_logs_created",
                count=len(logs_data),
                run_id=logs_data[0].get("run_id") if logs_data else None,
            )

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "bulk_create_google_api_logs_failed",
                count=len(logs_data),
                run_id=logs_data[0].get("run_id") if logs_data else None,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def create_log(
        self,
        user_id: UUID,
        run_id: str,
        api_name: str,
        endpoint: str,
        cost_usd: float,
        cost_eur: float,
        usd_to_eur_rate: float,
        cached: bool = False,
    ) -> GoogleApiUsageLog:
        """
        Create a single usage log.

        Args:
            user_id: User UUID
            run_id: LangGraph run_id or synthetic ID
            api_name: API identifier
            endpoint: Endpoint called
            cost_usd: Cost in USD
            cost_eur: Cost in EUR
            usd_to_eur_rate: Exchange rate used
            cached: Whether result was from cache

        Returns:
            Created GoogleApiUsageLog instance.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            log = GoogleApiUsageLog(
                user_id=user_id,
                run_id=run_id,
                api_name=api_name,
                endpoint=endpoint,
                cost_usd=cost_usd,
                cost_eur=cost_eur,
                usd_to_eur_rate=usd_to_eur_rate,
                cached=cached,
            )
            self.db.add(log)
            await self.db.flush()

            logger.info(
                "google_api_usage_log_created",
                user_id=str(user_id),
                api_name=api_name,
                endpoint=endpoint,
                cost_eur=float(cost_eur),
            )

            return log

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "create_google_api_log_failed",
                user_id=str(user_id),
                api_name=api_name,
                endpoint=endpoint,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise

    async def get_logs_by_run_id(self, run_id: str) -> list[GoogleApiUsageLog]:
        """
        Get all logs for a specific run (debug/audit).

        Args:
            run_id: LangGraph run_id or synthetic ID

        Returns:
            List of GoogleApiUsageLog entries for this run.

        Raises:
            SQLAlchemyError: On database error.
        """
        try:
            result = await self.db.execute(
                select(GoogleApiUsageLog)
                .where(GoogleApiUsageLog.run_id == run_id)
                .order_by(GoogleApiUsageLog.created_at)
            )
            logs = list(result.scalars().all())

            logger.debug(
                "google_api_logs_retrieved",
                run_id=run_id,
                count=len(logs),
            )

            return logs

        except (SQLAlchemyError, IntegrityError, OperationalError) as e:
            logger.error(
                "get_google_api_logs_failed",
                run_id=run_id,
                error_type=type(e).__name__,
                error=str(e),
            )
            raise
