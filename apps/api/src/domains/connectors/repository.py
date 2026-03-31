"""
Connectors repository for database operations.
Implements Repository pattern for Connector model CRUD operations.

Refactored (v0.4.1): Extends BaseRepository to reduce code duplication.
Common CRUD operations (get_by_id, create, update, delete) inherited from BaseRepository.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.repository import BaseRepository
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
)

logger = structlog.get_logger(__name__)


class ConnectorRepository(BaseRepository[Connector]):
    """
    Repository for connector database operations.

    Extends BaseRepository[Connector] for common CRUD operations.
    Adds domain-specific query methods for connectors.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, Connector)

    async def get_by_user_and_type(
        self, user_id: UUID, connector_type: ConnectorType
    ) -> Connector | None:
        """
        Get connector by user ID and connector type.

        Args:
            user_id: User UUID
            connector_type: Type of connector

        Returns:
            Connector object or None if not found
        """
        result = await self.db.execute(
            select(Connector).where(
                Connector.user_id == user_id,
                Connector.connector_type == connector_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_all_by_user(
        self,
        user_id: UUID,
        status: ConnectorStatus | None = None,
    ) -> list[Connector]:
        """
        Get all connectors for a user.

        Args:
            user_id: User UUID
            status: Optional status filter

        Returns:
            List of Connector objects
        """
        query = select(Connector).where(Connector.user_id == user_id)

        if status:
            query = query.where(Connector.status == status)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # Note: create(), update(), delete() inherited from BaseRepository

    async def revoke(self, connector: Connector) -> Connector:
        """
        Revoke a connector (set status to REVOKED).

        Args:
            connector: Connector object to revoke

        Returns:
            Revoked Connector object
        """
        connector.status = ConnectorStatus.REVOKED
        await self.db.flush()
        await self.db.refresh(connector)

        logger.info(
            "connector_revoked",
            connector_id=str(connector.id),
            connector_type=connector.connector_type,
        )
        return connector

    async def update_credentials(
        self, connector: Connector, encrypted_credentials: str
    ) -> Connector:
        """
        Update connector encrypted credentials.

        Args:
            connector: Connector object
            encrypted_credentials: New encrypted credentials

        Returns:
            Updated Connector object
        """
        connector.credentials_encrypted = encrypted_credentials
        await self.db.flush()
        await self.db.refresh(connector)

        logger.info("connector_credentials_updated", connector_id=str(connector.id))
        return connector

    # ========== GLOBAL CONFIG METHODS ==========

    async def get_all_global_configs(self) -> list[ConnectorGlobalConfig]:
        """
        Get all connector global configurations.

        Returns:
            List of all ConnectorGlobalConfig objects
        """
        result = await self.db.execute(
            select(ConnectorGlobalConfig).order_by(ConnectorGlobalConfig.connector_type)
        )
        return list(result.scalars().all())

    async def get_global_config_by_type(
        self, connector_type: ConnectorType
    ) -> ConnectorGlobalConfig | None:
        """
        Get global config by connector type.

        Args:
            connector_type: Type of connector

        Returns:
            ConnectorGlobalConfig or None if not found
        """
        result = await self.db.execute(
            select(ConnectorGlobalConfig).where(
                ConnectorGlobalConfig.connector_type == connector_type
            )
        )
        return result.scalar_one_or_none()

    async def create_global_config(
        self, connector_type: ConnectorType, is_enabled: bool, disabled_reason: str | None = None
    ) -> ConnectorGlobalConfig:
        """
        Create global config for connector type.

        Args:
            connector_type: Type of connector
            is_enabled: Whether connector is enabled
            disabled_reason: Reason for disabling (if disabled)

        Returns:
            Created ConnectorGlobalConfig object
        """
        config = ConnectorGlobalConfig(
            connector_type=connector_type,
            is_enabled=is_enabled,
            disabled_reason=disabled_reason,
        )
        self.db.add(config)
        await self.db.flush()
        await self.db.refresh(config)

        logger.info(
            "connector_global_config_created",
            connector_type=connector_type.value,
            is_enabled=is_enabled,
        )
        return config

    async def update_global_config(
        self, connector_type: ConnectorType, is_enabled: bool, disabled_reason: str | None = None
    ) -> ConnectorGlobalConfig:
        """
        Update global config for connector type.

        Args:
            connector_type: Type of connector
            is_enabled: Whether connector is enabled
            disabled_reason: Reason for disabling (if disabled)

        Returns:
            Updated ConnectorGlobalConfig object
        """
        result = await self.db.execute(
            select(ConnectorGlobalConfig).where(
                ConnectorGlobalConfig.connector_type == connector_type
            )
        )
        config = result.scalar_one()

        config.is_enabled = is_enabled
        config.disabled_reason = disabled_reason

        await self.db.flush()
        await self.db.refresh(config)

        logger.info(
            "connector_global_config_updated",
            connector_type=connector_type.value,
            is_enabled=is_enabled,
        )
        return config

    async def get_all_connectors_by_type(
        self, connector_type: ConnectorType, status: ConnectorStatus | None = None
    ) -> list[Connector]:
        """
        Get all connectors of a specific type (across all users).

        Args:
            connector_type: Type of connector
            status: Optional status filter

        Returns:
            List of Connector objects with user relationship eagerly loaded

        Note:
            Uses selectinload to eagerly load user relationship.
            This prevents MissingGreenlet errors and enables email notifications.
        """
        query = (
            select(Connector)
            .where(Connector.connector_type == connector_type)
            .options(selectinload(Connector.user))
        )

        if status:
            query = query.where(Connector.status == status)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_oauth_connectors_by_statuses(
        self,
        statuses: list[ConnectorStatus],
    ) -> list[Connector]:
        """
        Get OAuth-based connectors filtered by statuses (across all users).

        Generic method for querying OAuth connectors with specific status filters.
        Used internally by specialized methods for token refresh and health check.

        Args:
            statuses: List of connector statuses to include in the query.

        Returns:
            List of Connector objects using OAuth authentication.
        """
        oauth_types = ConnectorType.get_oauth_types()

        query = select(Connector).where(
            Connector.status.in_(statuses),
            Connector.connector_type.in_(oauth_types),
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_active_oauth_connectors(self) -> list[Connector]:
        """
        Get active OAuth connectors for active, non-deleted users only.

        Used by proactive token refresh background job to find connectors
        that may need token refresh before expiration. Excludes connectors
        for deactivated or deleted users to avoid unnecessary API calls.

        Returns:
            List of active Connector objects using OAuth authentication.
        """
        from src.domains.auth.models import User

        oauth_types = ConnectorType.get_oauth_types()

        query = (
            select(Connector)
            .join(User, Connector.user_id == User.id)
            .where(
                Connector.status == ConnectorStatus.ACTIVE,
                Connector.connector_type.in_(oauth_types),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_oauth_connectors_for_health_check(self) -> list[Connector]:
        """
        Get OAuth-based connectors for health check, excluding blocked/inactive users.

        Used by OAuth health check background job to find connectors
        that may need user notification (ERROR status).

        Returns connectors with status ACTIVE or ERROR (not INACTIVE/REVOKED),
        only for users where:
        - User.is_active = True (not deactivated)
        - User.deleted_at IS NULL (not deleted)
        - UserUsageLimit.is_usage_blocked = False OR no usage limit record exists

        Returns:
            List of Connector objects using OAuth authentication.
        """
        from sqlalchemy import or_

        from src.domains.auth.models import User
        from src.domains.usage_limits.models import UserUsageLimit

        oauth_types = ConnectorType.get_oauth_types()

        query = (
            select(Connector)
            .join(User, Connector.user_id == User.id)
            .outerjoin(UserUsageLimit, User.id == UserUsageLimit.user_id)
            .where(
                Connector.status.in_([ConnectorStatus.ACTIVE, ConnectorStatus.ERROR]),
                Connector.connector_type.in_(oauth_types),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                or_(
                    UserUsageLimit.is_usage_blocked.is_(False),
                    UserUsageLimit.is_usage_blocked.is_(None),
                ),
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())
