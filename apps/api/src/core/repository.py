"""
Generic base repository implementing common CRUD operations.

This module provides a type-safe, generic repository pattern that reduces
code duplication across domain-specific repositories.

Best Practices:
- Type safety with Generic[ModelType]
- Soft delete support (is_active filter)
- Structured logging for all operations
- Fail-secure defaults
- SQLAlchemy async pattern
- Standardized pagination with PaginationResult
- Prometheus metrics instrumentation for performance monitoring
"""

import time
from typing import Any, TypeVar
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.core.field_names import FIELD_IS_ACTIVE
from src.core.pagination_helpers import (
    PaginationResult,
    calculate_total_pages,
    validate_pagination,
)

logger = structlog.get_logger(__name__)

# Generic type variable for SQLAlchemy models
ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class BaseRepository[ModelType: DeclarativeBase]:
    """
    Generic repository for common CRUD operations.

    This base class provides standard database operations that are common
    across all domain repositories, reducing code duplication and ensuring
    consistency.

    Type Parameters:
        ModelType: SQLAlchemy model class (must inherit from DeclarativeBase)

    Features:
        - Type-safe operations with Generic[ModelType]
        - Soft delete support (exclude is_active=False by default)
        - Structured logging for observability
        - Async SQLAlchemy patterns
        - Optimized queries (no N+1 issues)

    Usage:
        >>> class UserRepository(BaseRepository[User]):
        ...     def __init__(self, db: AsyncSession):
        ...         super().__init__(db, User)
        ...
        ...     # Add domain-specific methods here
        ...     async def get_by_email(self, email: str) -> User | None:
        ...         ...
    """

    def __init__(self, db: AsyncSession, model: type[ModelType]) -> None:
        """
        Initialize repository with database session and model class.

        Args:
            db: SQLAlchemy async session
            model: SQLAlchemy model class (e.g., User, Connector)
        """
        self.db = db
        self.model = model
        self.model_name = model.__name__

    @staticmethod
    def _classify_db_error(error: Exception) -> str:
        """
        Classify database errors into standardized categories for metrics.

        Error taxonomy for observability:
        - deadlock: Concurrent transaction conflicts (PostgreSQL 40P01)
        - timeout: Query or connection timeouts (statement_timeout, lock_timeout)
        - constraint_violation: Unique/FK/Check constraint failures
        - serialization_failure: Transaction isolation conflicts (PostgreSQL 40001)
        - connection_error: Connection pool exhaustion, network failures
        - unknown: Other database errors

        Args:
            error: SQLAlchemy exception

        Returns:
            Error type string for metrics labeling
        """
        if isinstance(error, IntegrityError):
            return "constraint_violation"

        if isinstance(error, OperationalError):
            error_msg = str(error).lower()

            # PostgreSQL deadlock error code 40P01
            if "deadlock" in error_msg or "40p01" in error_msg:
                return "deadlock"

            # PostgreSQL serialization failure 40001
            if "serialization failure" in error_msg or "40001" in error_msg:
                return "serialization_failure"

            # Timeout errors
            if any(
                keyword in error_msg for keyword in ["timeout", "timed out", "connection refused"]
            ):
                return "timeout"

            # Connection pool errors
            if any(keyword in error_msg for keyword in ["connection", "pool", "max_overflow"]):
                return "connection_error"

        if isinstance(error, DBAPIError):
            return "connection_error"

        return "unknown"

    async def get_by_id(
        self,
        id: UUID,
        include_inactive: bool = False,
    ) -> ModelType | None:
        """
        Get model by ID.

        Best Practices:
        - Soft delete aware (excludes is_active=False by default)
        - Returns None if not found (fail-secure)
        - Structured logging for observability
        - Prometheus metrics for query performance

        Args:
            id: Model UUID
            include_inactive: If False (default), exclude soft-deleted records

        Returns:
            Model instance or None if not found

        Example:
            >>> user = await repo.get_by_id(user_id)
            >>> if user:
            ...     print(f"Found: {user.email}")
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            query = select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]

            # Soft delete filter (if model has is_active column)
            if not include_inactive and hasattr(self.model, "is_active"):
                query = query.where(self.model.is_active)  # type: ignore[attr-defined]

            result = await self.db.execute(query)
            instance = result.scalar_one_or_none()

            if instance:
                logger.debug(
                    f"{self.model_name.lower()}_fetched_by_id",
                    model=self.model_name,
                    id=str(id),
                    include_inactive=include_inactive,
                )

            return instance

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="get_by_id",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="get_by_id",
                query_type="select",
            ).observe(duration)

    async def get_all(
        self,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ModelType]:
        """
        Get all model instances with optional pagination.

        Best Practices:
        - Soft delete aware
        - Pagination support for large datasets
        - Prevents memory issues with large tables
        - Prometheus metrics for query performance

        Args:
            include_inactive: If False (default), exclude soft-deleted records
            limit: Maximum number of results (None = no limit)
            offset: Number of results to skip (for pagination)

        Returns:
            List of model instances

        Example:
            >>> # Get first 50 active users
            >>> users = await repo.get_all(limit=50, offset=0)
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            query = select(self.model)

            # Soft delete filter
            if not include_inactive and hasattr(self.model, "is_active"):
                query = query.where(self.model.is_active)  # type: ignore[attr-defined]

            if limit is not None:
                query = query.limit(limit)

            if offset is not None:
                query = query.offset(offset)

            result = await self.db.execute(query)
            instances = list(result.scalars().all())

            logger.debug(
                f"{self.model_name.lower()}s_fetched_all",
                model=self.model_name,
                count=len(instances),
                include_inactive=include_inactive,
                limit=limit,
                offset=offset,
            )

            return instances

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="get_all",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="get_all",
                query_type="select",
            ).observe(duration)

    async def create(self, data: dict[str, Any]) -> ModelType:
        """
        Create a new model instance.

        Best Practices:
        - Uses flush() + refresh() for immediate ID availability
        - Structured logging for audit trail
        - Type-safe return value
        - Prometheus metrics for query performance

        Args:
            data: Dictionary of model fields

        Returns:
            Created model instance with ID populated

        Example:
            >>> user = await repo.create({
            ...     "email": "user@example.com",
            ...     "full_name": "John Doe",
            ...     "is_active": True,
            ... })
            >>> print(user.id)  # UUID available immediately

        Note:
            Requires db.commit() to persist to database.
            Use flush() + refresh() pattern for ID generation.
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            instance = self.model(**data)
            self.db.add(instance)
            await self.db.flush()
            await self.db.refresh(instance)

            logger.info(
                f"{self.model_name.lower()}_created",
                model=self.model_name,
                id=str(instance.id),  # type: ignore[attr-defined]
            )

            return instance

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="create",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="create",
                query_type="insert",
            ).observe(duration)

    async def update(
        self,
        instance: ModelType,
        data: dict[str, Any],
    ) -> ModelType:
        """
        Update a model instance.

        Best Practices:
        - Only updates provided fields (partial update)
        - Uses flush() + refresh() for immediate reflection
        - Structured logging for audit trail
        - Prometheus metrics for query performance

        Args:
            instance: Model instance to update
            data: Dictionary of fields to update

        Returns:
            Updated model instance

        Example:
            >>> user = await repo.get_by_id(user_id)
            >>> updated_user = await repo.update(user, {
            ...     "full_name": "Jane Doe",
            ...     "is_verified": True,
            ... })

        Note:
            Requires db.commit() to persist to database.
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            for key, value in data.items():
                setattr(instance, key, value)

            await self.db.flush()
            await self.db.refresh(instance)

            logger.info(
                f"{self.model_name.lower()}_updated",
                model=self.model_name,
                id=str(instance.id),  # type: ignore[attr-defined]
                updated_fields=list(data.keys()),
            )

            return instance

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="update",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="update",
                query_type="update",
            ).observe(duration)

    async def delete(self, instance: ModelType) -> None:
        """
        Delete a model instance (hard delete).

        For soft delete, use update() with is_active=False instead.

        Best Practices:
        - Hard delete (permanent removal from database)
        - Structured logging for audit trail
        - Use soft delete for data retention requirements
        - Prometheus metrics for query performance

        Args:
            instance: Model instance to delete

        Example:
            >>> user = await repo.get_by_id(user_id)
            >>> await repo.delete(user)
            >>> await db.commit()

        Note:
            Requires db.commit() to persist to database.
            For soft delete: await repo.update(instance, {"is_active": False})
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            await self.db.delete(instance)

            logger.info(
                f"{self.model_name.lower()}_deleted",
                model=self.model_name,
                id=str(instance.id),  # type: ignore[attr-defined]
            )

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="delete",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="delete",
                query_type="delete",
            ).observe(duration)

    async def count(self, include_inactive: bool = False) -> int:
        """
        Count total number of model instances.

        Args:
            include_inactive: If False (default), exclude soft-deleted records

        Returns:
            Total count

        Example:
            >>> total_users = await repo.count()
            >>> all_users = await repo.count(include_inactive=True)
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model)

        if not include_inactive and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active)  # type: ignore[attr-defined]

        result = await self.db.execute(query)
        count = result.scalar_one()

        logger.debug(
            f"{self.model_name.lower()}_counted",
            model=self.model_name,
            count=count,
            include_inactive=include_inactive,
        )

        return count

    async def get_or_create(
        self,
        defaults: dict[str, Any],
        **filters: Any,
    ) -> tuple[ModelType, bool]:
        """
        Get existing instance or create new one.

        Useful pattern for idempotent operations where you want to ensure
        an entity exists without risking duplicate creation errors.

        Args:
            defaults: Default values to use if creating new instance
            **filters: Filter criteria to find existing instance

        Returns:
            Tuple of (instance, created) where:
            - instance: The model instance (existing or newly created)
            - created: True if new instance was created, False if existing

        Example:
            >>> user, created = await repo.get_or_create(
            ...     defaults={"full_name": "John Doe", "is_active": True},
            ...     email="user@example.com"
            ... )
            >>> if created:
            ...     print("New user created")
            ... else:
            ...     print("Existing user found")

        Note:
            Requires db.commit() to persist new instances to database.
        """
        from sqlalchemy import and_

        # Build query from filters
        query = select(self.model)
        conditions = [getattr(self.model, key) == value for key, value in filters.items()]
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        instance = result.scalar_one_or_none()

        if instance:
            logger.debug(
                f"{self.model_name.lower()}_found_existing",
                model=self.model_name,
                filters=filters,
            )
            return instance, False

        # Create new instance
        create_data = {**filters, **defaults}
        new_instance = await self.create(create_data)

        logger.info(
            f"{self.model_name.lower()}_created_via_get_or_create",
            model=self.model_name,
            id=str(new_instance.id),  # type: ignore[attr-defined]
        )

        return new_instance, True

    async def bulk_create(
        self,
        items: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> list[ModelType]:
        """
        Create multiple instances efficiently in batches.

        Best practice for inserting large numbers of records while avoiding
        memory issues and database connection timeouts.

        Args:
            items: List of dictionaries containing model field data
            batch_size: Number of items to insert per batch (default: 100)

        Returns:
            List of created model instances with IDs populated

        Example:
            >>> users_data = [
            ...     {"email": "user1@example.com", "full_name": "User 1"},
            ...     {"email": "user2@example.com", "full_name": "User 2"},
            ...     # ... 1000 more users
            ... ]
            >>> created_users = await repo.bulk_create(users_data, batch_size=100)
            >>> print(f"Created {len(created_users)} users")

        Note:
            - Requires db.commit() to persist to database
            - Uses flush() to get IDs without committing
            - Batching prevents memory issues with large datasets
        """
        all_instances: list[ModelType] = []

        # Process in batches to avoid memory issues
        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            batch_instances = [self.model(**item) for item in batch]

            self.db.add_all(batch_instances)
            await self.db.flush()

            # Refresh to get IDs
            for instance in batch_instances:
                await self.db.refresh(instance)

            all_instances.extend(batch_instances)

            logger.debug(
                f"{self.model_name.lower()}_bulk_created_batch",
                model=self.model_name,
                batch_num=i // batch_size + 1,
                batch_size=len(batch),
            )

        logger.info(
            f"{self.model_name.lower()}_bulk_created",
            model=self.model_name,
            total_created=len(all_instances),
            num_batches=(len(items) + batch_size - 1) // batch_size,
        )

        return all_instances

    async def soft_delete(self, instance: ModelType) -> ModelType:
        """
        Soft delete an instance by setting is_active=False.

        Preserves data for audit trails and potential recovery while
        logically removing it from normal queries.

        Args:
            instance: Model instance to soft delete

        Returns:
            Updated model instance with is_active=False

        Raises:
            AttributeError: If model doesn't have is_active field

        Example:
            >>> user = await repo.get_by_id(user_id)
            >>> deleted_user = await repo.soft_delete(user)
            >>> await db.commit()
            >>> # User is now excluded from get_by_id() calls

        Note:
            - Requires db.commit() to persist to database
            - Only works with models that have is_active field
            - For hard delete, use delete() method instead
        """
        if not hasattr(instance, "is_active"):
            raise AttributeError(
                f"{self.model_name} does not support soft delete (no is_active field)"
            )

        return await self.update(instance, {FIELD_IS_ACTIVE: False})

    async def count_by_criteria(self, **filters: Any) -> int:
        """
        Count instances matching specific criteria.

        Args:
            **filters: Filter criteria (e.g., is_verified=True, role="admin")

        Returns:
            Count of matching instances

        Example:
            >>> # Count verified users
            >>> verified_count = await repo.count_by_criteria(is_verified=True)
            >>> # Count admin users
            >>> admin_count = await repo.count_by_criteria(role="admin")
        """
        from sqlalchemy import and_, func

        query = select(func.count()).select_from(self.model)

        conditions = [getattr(self.model, key) == value for key, value in filters.items()]
        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        count = result.scalar_one()

        logger.debug(
            f"{self.model_name.lower()}_counted_by_criteria",
            model=self.model_name,
            filters=filters,
            count=count,
        )

        return count

    async def get_by_email(self, email: str) -> ModelType | None:
        """
        Get model by email address.

        Common pattern for User models. Returns None if not found.

        Args:
            email: Email address to search for

        Returns:
            Model instance or None if not found

        Example:
            >>> user = await repo.get_by_email("user@example.com")
            >>> if user:
            ...     print(f"Found: {user.full_name}")

        Note:
            - Only works with models that have an 'email' field
            - Returns first match (assumes email is unique)
        """
        from src.infrastructure.observability.metrics_database import (
            db_query_errors_total,
            repository_query_duration_seconds,
        )

        start_time = time.time()

        try:
            query = select(self.model).where(self.model.email == email)  # type: ignore[attr-defined]
            result = await self.db.execute(query)
            instance = result.scalar_one_or_none()

            if instance:
                logger.debug(
                    f"{self.model_name.lower()}_fetched_by_email",
                    model=self.model_name,
                    email=email,
                )

            return instance

        except SQLAlchemyError as e:
            error_type = self._classify_db_error(e)
            db_query_errors_total.labels(repository=self.model_name, error_type=error_type).inc()

            logger.error(
                "repository_query_error",
                repository=self.model_name,
                method="get_by_email",
                error_type=error_type,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            duration = time.time() - start_time
            repository_query_duration_seconds.labels(
                repository=self.model_name,
                method="get_by_email",
                query_type="select",
            ).observe(duration)

    async def get_paginated(
        self,
        page: int,
        page_size: int,
        include_inactive: bool = False,
        **filters: Any,
    ) -> PaginationResult[ModelType]:
        """
        Get paginated results with standardized PaginationResult.

        This method provides a complete pagination solution with validation,
        filtering, and metadata in a single call.

        Args:
            page: Page number (1-indexed, will be validated)
            page_size: Items per page (will be validated)
            include_inactive: If False (default), exclude soft-deleted records
            **filters: Additional filter criteria (e.g., role="admin", is_verified=True)

        Returns:
            PaginationResult with items, total count, and pagination metadata

        Example:
            >>> # Get page 2 of active verified users, 50 per page
            >>> result = await repo.get_paginated(
            ...     page=2,
            ...     page_size=50,
            ...     include_inactive=False,
            ...     is_verified=True
            ... )
            >>> print(f"Showing {len(result.items)} of {result.total} total")
            >>> print(f"Page {result.page} of {result.total_pages}")
            >>> print(f"Has next: {result.has_next}")

        Note:
            - Page and page_size are automatically validated
            - Soft delete filter applies unless include_inactive=True
            - Returns empty list if page exceeds total_pages
        """
        from sqlalchemy import and_, func

        # Validate pagination params
        validated_page, validated_page_size = validate_pagination(page, page_size)

        # Build base query
        query = select(self.model)

        # Build filter conditions
        conditions = []

        # Soft delete filter
        if not include_inactive and hasattr(self.model, "is_active"):
            conditions.append(self.model.is_active)  # type: ignore[attr-defined]

        # Additional filters
        for key, value in filters.items():
            conditions.append(getattr(self.model, key) == value)

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(self.model)
        if conditions:
            count_query = count_query.where(and_(*conditions))

        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        # Calculate pagination
        total_pages = calculate_total_pages(total, validated_page_size)
        skip = (validated_page - 1) * validated_page_size

        # Apply pagination
        query = query.offset(skip).limit(validated_page_size)

        # Execute query
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        logger.debug(
            f"{self.model_name.lower()}_paginated",
            model=self.model_name,
            page=validated_page,
            page_size=validated_page_size,
            total=total,
            total_pages=total_pages,
            returned_count=len(items),
            include_inactive=include_inactive,
            filters=filters,
        )

        return PaginationResult(
            items=items,
            total=total,
            page=validated_page,
            page_size=validated_page_size,
            total_pages=total_pages,
        )
