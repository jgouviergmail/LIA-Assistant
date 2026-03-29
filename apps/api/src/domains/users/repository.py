"""
Users repository for database operations.
Implements Repository pattern for User model CRUD operations.

Refactored (v0.4.1): Extends BaseRepository to reduce code duplication.
Common CRUD operations inherited from BaseRepository with domain-specific overrides.

REFACTORED (2025-11-16 - Session 15 - Phase 2):
Removed duplicated methods now provided by BaseRepository:
- get_by_email() - Inherited from BaseRepository
- soft_delete() - Inherited from BaseRepository (sets is_active=False)
- delete() - Inherited from BaseRepository (hard delete)

This eliminates 34 lines of duplicated CRUD code between AuthRepository and UserRepository.
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.repository import BaseRepository
from src.domains.auth.models import User
from src.domains.chat.models import MessageTokenSummary, UserStatistics
from src.domains.connectors.models import Connector, ConnectorStatus
from src.domains.users.models import AdminAuditLog

logger = structlog.get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """
    Repository for user management database operations.

    Extends BaseRepository[User] for common CRUD operations.
    Overrides get_by_id() to eagerly load connectors relationship.
    """

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db, User)

    async def get_by_id(self, user_id: UUID, include_inactive: bool = False) -> User | None:
        """
        Get user by ID with connectors eagerly loaded.

        Overrides BaseRepository.get_by_id() to add selectinload(User.connectors).

        Args:
            user_id: User UUID
            include_inactive: If False (default), exclude users with is_active=False

        Returns:
            User object with connectors loaded, or None if not found

        Note:
            Uses selectinload to eagerly load connectors relationship.
            This prevents MissingGreenlet errors in async context.
            By default, inactive (soft-deleted) users are excluded.
        """
        query = select(User).where(User.id == user_id).options(selectinload(User.connectors))

        if not include_inactive:
            query = query.where(User.is_active)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_minimal_for_session(self, user_id: UUID) -> User | None:
        """
        Get user with minimal fields for session authentication (OPTIMIZED).

        Optimized query for session validation:
        - No selectinload(connectors) - reduces query complexity
        - Returns user regardless of is_active status (check done in session_dependencies)
        - Uses PRIMARY KEY index (fastest possible lookup)

        Performance:
            - PostgreSQL SELECT: ~0.3-0.5ms (vs 0.5-1ms with selectinload)
            - Connection pool: reuses existing connections (asyncpg)
            - Total latency: ~0.5ms per authenticated request

        Args:
            user_id: User UUID

        Returns:
            User object (no connectors loaded) or None if not found

        Usage:
            Used by session_dependencies.get_current_session() to fetch User
            from minimal session (session stores user_id only, not full User object).

        Security:
            - is_active check delegated to get_current_active_session (raises 403)
            - Single source of truth: PostgreSQL (not Redis cached User data)
        """
        query = select(User).where(User.id == user_id)
        # No selectinload(User.connectors) for session validation (performance optimization)

        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if user:
            logger.debug(
                "user_fetched_for_session",
                user_id=str(user_id),
                email=user.email,
                is_verified=user.is_verified,
                is_superuser=user.is_superuser,
            )

        return user

    # Note: get_by_email() inherited from BaseRepository

    async def count_user_connectors(self, user_id: UUID) -> int:
        """
        Count the number of connectors for a user.

        Args:
            user_id: User UUID

        Returns:
            Number of connectors owned by the user

        Note:
            Uses an efficient COUNT query without loading connector objects.
            Preferred over len(user.connectors) for performance.
        """
        from src.domains.connectors.models import Connector

        result = await self.db.execute(
            select(func.count()).select_from(Connector).where(Connector.user_id == user_id)
        )
        return result.scalar_one()

    async def get_all_with_count(
        self,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
    ) -> tuple[list[User], int]:
        """
        Get all users with pagination and total count.

        This method provides both paginated results and total count in a single call,
        optimized for admin interfaces that need both values.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            is_active: Filter by active status (optional)

        Returns:
            Tuple of (list of users, total count)

        Note:
            This method differs from BaseRepository.get_all() by returning a tuple
            with count. For simple list retrieval, use the inherited get_all() method.
        """
        # Build query
        query = select(User)

        # Apply filters
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute query
        result = await self.db.execute(query)
        users = list(result.scalars().all())

        logger.info("users_fetched", count=len(users), total=total)

        return users, total

    # Note: update() inherited from BaseRepository

    async def delete(self, user: User) -> None:
        """
        Delete a user (soft delete by setting is_active=False).

        This method provides the domain-specific soft delete API for User models.
        Internally delegates to BaseRepository.soft_delete().

        Args:
            user: User object to delete
        """
        await self.soft_delete(user)
        logger.info("user_deleted", user_id=str(user.id))

    async def hard_delete(self, user: User) -> None:
        """
        Permanently delete a user from database.

        This method provides the domain-specific hard delete API for User models.
        Internally delegates to BaseRepository.delete().

        Args:
            user: User object to delete
        """
        await BaseRepository.delete(self, user)
        logger.info("user_hard_deleted", user_id=str(user.id))

    async def search_by_email(self, email_pattern: str) -> list[User]:
        """
        Search users by email pattern.

        Args:
            email_pattern: Email pattern to search for (e.g., '%@example.com')

        Returns:
            List of matching users
        """
        result = await self.db.execute(select(User).where(User.email.ilike(email_pattern)))
        return list(result.scalars().all())

    async def search_for_autocomplete(self, query: str, limit: int = 10) -> list[User]:
        """
        Search users by email or full_name for autocomplete (admin only).

        Searches both email and full_name fields case-insensitively and accent-insensitively.
        Uses PostgreSQL unaccent() extension to ignore diacritical marks.
        Returns both active and inactive users.

        Args:
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching users (up to limit)
        """
        pattern = f"%{query}%"
        # Use unaccent() for accent-insensitive search (e.g., "Gerard" matches "Gérard")
        stmt = (
            select(User)
            .where(
                or_(
                    func.unaccent(User.email).ilike(func.unaccent(pattern)),
                    func.unaccent(User.full_name).ilike(func.unaccent(pattern)),
                )
            )
            .order_by(User.email.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_user_ids(self) -> list[UUID]:
        """
        Get IDs of all active users.

        Used for broadcasting messages to all users.

        Returns:
            List of active user UUIDs
        """
        stmt = select(User.id).where(User.is_active.is_(True))
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    @staticmethod
    def _group_users_by_language(
        rows: Sequence[tuple[UUID, str]],
    ) -> dict[str, list[UUID]]:
        """
        Group user IDs by their language preference.

        Args:
            rows: List of (user_id, language) tuples from query result

        Returns:
            Dict mapping language code to list of user UUIDs.
        """
        grouped: dict[str, list[UUID]] = {}
        for user_id, language in rows:
            if language not in grouped:
                grouped[language] = []
            grouped[language].append(user_id)
        return grouped

    async def get_active_users_grouped_by_language(self) -> dict[str, list[UUID]]:
        """
        Get all active users grouped by their language preference.

        Used for sending translated broadcast messages to users in their preferred language.

        Returns:
            Dict mapping language code to list of user UUIDs.
            Example: {"fr": [uuid1, uuid2], "en": [uuid3]}
        """
        stmt = select(User.id, User.language).where(User.is_active.is_(True))
        result = await self.db.execute(stmt)
        # Convert Row objects to tuples for type safety
        rows: list[tuple[UUID, str]] = [(row[0], row[1]) for row in result.all()]
        return self._group_users_by_language(rows)

    async def get_selected_users_grouped_by_language(
        self, user_ids: list[UUID]
    ) -> dict[str, list[UUID]]:
        """
        Get selected users grouped by their language preference.

        Used for sending targeted broadcast messages to specific users.
        Only includes active users from the provided list.

        Args:
            user_ids: List of user UUIDs to filter by

        Returns:
            Dict mapping language code to list of user UUIDs.
            Example: {"fr": [uuid1, uuid2], "en": [uuid3]}
        """
        stmt = (
            select(User.id, User.language)
            .where(User.is_active.is_(True))
            .where(User.id.in_(user_ids))
        )
        result = await self.db.execute(stmt)
        # Convert Row objects to tuples for type safety
        rows: list[tuple[UUID, str]] = [(row[0], row[1]) for row in result.all()]
        return self._group_users_by_language(rows)

    # ========== ADMIN METHODS ==========

    async def get_users_paginated(
        self,
        filters: list,
        page: int,
        page_size: int,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[User]:
        """
        Get paginated users with filters and sorting.

        Args:
            filters: List of SQLAlchemy filter expressions
            page: Page number (1-indexed)
            page_size: Items per page
            sort_by: Column name to sort by
            sort_order: Sort order ('asc' or 'desc')

        Returns:
            List of User objects
        """
        offset = (page - 1) * page_size

        # Build base query
        stmt = select(User).where(*filters)

        # Apply dynamic sorting
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_order.lower() == "desc":
            stmt = stmt.order_by(sort_column.desc())
        else:
            stmt = stmt.order_by(sort_column.asc())

        # Apply pagination
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_users(self, filters: list) -> int:
        """
        Count total users matching filters.

        Args:
            filters: List of SQLAlchemy filter expressions

        Returns:
            Total count of matching users
        """
        stmt = select(func.count(User.id)).where(*filters)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_users_with_stats_paginated(
        self,
        filters: list,
        page: int,
        page_size: int,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[tuple[User, UserStatistics | None, int, datetime | None, int, int, int, int, bool]]:
        """
        Get paginated users with their statistics and additional counts.

        Args:
            filters: List of SQLAlchemy filter expressions
            page: Page number (1-indexed)
            page_size: Items per page
            sort_by: Column name to sort by
            sort_order: Sort order ('asc' or 'desc')

        Returns:
            List of tuples (User, UserStatistics or None, active_connectors_count,
            last_message_at, skills_count, mcp_servers_count, scheduled_actions_count,
            rag_spaces_count, is_usage_blocked)
        """
        # Late imports to avoid circular dependencies
        from src.domains.rag_spaces.models import RAGSpace
        from src.domains.scheduled_actions.models import ScheduledAction
        from src.domains.skills.models import Skill
        from src.domains.usage_limits.models import UserUsageLimit
        from src.domains.user_mcp.models import UserMCPServer

        offset = (page - 1) * page_size

        # Subquery for active connectors count
        active_connectors_subq = (
            select(func.count(Connector.id))
            .where(Connector.user_id == User.id)
            .where(Connector.status == ConnectorStatus.ACTIVE)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for last message timestamp
        last_message_subq = (
            select(func.max(MessageTokenSummary.created_at))
            .where(MessageTokenSummary.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for user-imported skills count (scope='user', owner_id matches)
        skills_count_subq = (
            select(func.count(Skill.id))
            .where(Skill.owner_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for user MCP servers count
        mcp_servers_count_subq = (
            select(func.count(UserMCPServer.id))
            .where(UserMCPServer.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for scheduled actions count
        scheduled_actions_count_subq = (
            select(func.count(ScheduledAction.id))
            .where(ScheduledAction.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for RAG spaces count
        rag_spaces_count_subq = (
            select(func.count(RAGSpace.id))
            .where(RAGSpace.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Subquery for is_usage_blocked
        is_usage_blocked_subq = (
            select(UserUsageLimit.is_usage_blocked)
            .where(UserUsageLimit.user_id == User.id)
            .correlate(User)
            .scalar_subquery()
        )

        # Build base query with LEFT JOIN to UserStatistics and subqueries
        stmt = (
            select(
                User,
                UserStatistics,
                active_connectors_subq.label("active_connectors_count"),
                last_message_subq.label("last_message_at"),
                skills_count_subq.label("skills_count"),
                mcp_servers_count_subq.label("mcp_servers_count"),
                scheduled_actions_count_subq.label("scheduled_actions_count"),
                rag_spaces_count_subq.label("rag_spaces_count"),
                is_usage_blocked_subq.label("is_usage_blocked"),
            )
            .outerjoin(UserStatistics, User.id == UserStatistics.user_id)
            .where(*filters)
        )

        # Apply dynamic sorting
        sort_column = getattr(User, sort_by, User.created_at)
        if sort_order.lower() == "desc":
            stmt = stmt.order_by(sort_column.desc())
        else:
            stmt = stmt.order_by(sort_column.asc())

        # Apply pagination
        stmt = stmt.offset(offset).limit(page_size)

        result = await self.db.execute(stmt)
        # Convert Row objects to tuples for proper typing
        return [
            (
                row[0],
                row[1],
                row[2] or 0,
                row[3],
                row[4] or 0,
                row[5] or 0,
                row[6] or 0,
                row[7] or 0,
                bool(row[8]),
            )
            for row in result.all()
        ]

    # ========== AUDIT LOG METHODS ==========

    async def create_audit_log(
        self,
        admin_user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminAuditLog:
        """
        Create an admin audit log entry.

        Args:
            admin_user_id: ID of admin performing action
            action: Action performed (e.g., 'user_deactivated')
            resource_type: Type of resource (e.g., 'user', 'connector')
            resource_id: ID of affected resource
            details: Additional details (JSON)
            ip_address: IP address of admin
            user_agent: User agent string

        Returns:
            Created AdminAuditLog object
        """
        audit_log = AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit_log)
        await self.db.flush()
        await self.db.refresh(audit_log)

        logger.info(
            "admin_audit_log_created",
            admin_user_id=str(admin_user_id),
            action=action,
            resource_type=resource_type,
        )
        return audit_log
