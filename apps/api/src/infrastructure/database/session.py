"""
Database session management using SQLAlchemy async engine.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import QueuePool

from src.core.config import settings
from src.infrastructure.observability.metrics_database import (
    db_connection_pool_checkedout,
    db_connection_pool_exhausted_total,
    db_connection_pool_overflow,
    db_connection_pool_size,
    db_connection_pool_waiting_total,
)

logger = structlog.get_logger(__name__)

# Create async engine with production-grade connection pooling
# Reference: https://docs.sqlalchemy.org/en/20/core/pooling.html
engine = create_async_engine(
    str(settings.database_url),
    echo=settings.log_level_sqlalchemy.upper() in ("DEBUG", "INFO"),
    # Pool sizing
    pool_size=settings.database_pool_size,  # Persistent connections
    max_overflow=settings.database_max_overflow,  # Burst capacity
    # Connection lifecycle
    pool_timeout=settings.database_pool_timeout,  # Fail-fast if pool exhausted
    pool_recycle=settings.database_pool_recycle,  # Avoid stale connections
    pool_pre_ping=True,  # Validate connections before use (recommended)
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for SQLAlchemy models
Base = declarative_base()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.
    Automatically handles session lifecycle and commits/rollbacks.

    Yields:
        AsyncSession: SQLAlchemy async session
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error("database_session_error", error=str(exc), exc_info=True)
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Database session context manager for non-FastAPI code.

    Use Cases:
    - LangChain tools (@tool decorated functions)
    - Background tasks (scheduler, workers)
    - Metrics collection
    - Any async code outside FastAPI request lifecycle

    For FastAPI endpoints, use Depends(get_db) instead.

    Example:
        async with get_db_context() as db:
            result = await db.execute(stmt)
            # Automatically commits on success, rollbacks on error

    Yields:
        AsyncSession: SQLAlchemy async session

    Raises:
        Exception: Any database error (logged and re-raised)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.error(
                "database_session_error",
                error=str(exc),
                error_type=type(exc).__name__,
                exc_info=True,
            )
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    Only use in development/testing - use Alembic migrations in production.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database_tables_created")


async def close_db() -> None:
    """Close database connection pool."""
    await engine.dispose()
    logger.info("database_connection_closed")


def update_db_pool_metrics() -> None:
    """
    Update database connection pool metrics for Prometheus.

    This function should be called periodically (e.g., from a background task)
    or from middleware to track pool health.

    Metrics updated:
    - db_connection_pool_checkedout: Current number of checked-out connections (in use)
    - db_connection_pool_size: Pool size (from settings)
    - db_connection_pool_overflow: Current overflow count (connections beyond pool_size)
    - db_connection_pool_waiting_total: Threads waiting for a connection (saturation)
    - db_connection_pool_exhausted_total: Total times pool was exhausted (all connections in use)

    Connection pool saturation detection:
    - If waiting > 0: Pool is saturated, requests are queuing
    - If overflow > 0: Pool has exceeded pool_size, using overflow connections
    - If checkedout == (pool_size + max_overflow): Pool is exhausted (503 risk)
    """
    try:
        pool = engine.pool
        if isinstance(pool, QueuePool):
            # Update checked-out connections (in use)
            checked_out = pool.checkedout()
            db_connection_pool_checkedout.set(checked_out)

            # Update pool size (configured maximum)
            db_connection_pool_size.set(settings.database_pool_size)

            # Update overflow count (connections beyond pool_size)
            overflow = pool.overflow()
            db_connection_pool_overflow.set(overflow if overflow > 0 else 0)

            # Update waiting count (threads waiting for connection - saturation indicator)
            # SQLAlchemy QueuePool doesn't expose waiting count directly
            # We can infer saturation if checked_out >= pool_size + overflow
            max_connections = settings.database_pool_size + settings.database_max_overflow
            if checked_out >= max_connections:
                # Pool is exhausted - all connections in use
                db_connection_pool_exhausted_total.inc()
                logger.warning(
                    "database_connection_pool_exhausted",
                    checked_out=checked_out,
                    max_connections=max_connections,
                    pool_size=settings.database_pool_size,
                    max_overflow=settings.database_max_overflow,
                )

            # Approximate waiting count: if we're at or near capacity, estimate saturation
            # This is a heuristic since SQLAlchemy doesn't expose exact waiting count
            saturation_threshold = int(max_connections * 0.9)  # 90% utilization
            if checked_out >= saturation_threshold:
                # Estimate waiting based on how close we are to exhaustion
                estimated_waiting = max(0, checked_out - saturation_threshold)
                db_connection_pool_waiting_total.set(estimated_waiting)
            else:
                db_connection_pool_waiting_total.set(0)

    except Exception as e:
        logger.warning("failed_to_update_db_pool_metrics", error=str(e))
