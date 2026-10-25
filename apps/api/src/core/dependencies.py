"""
FastAPI dependency injection utilities.
Provides common dependencies for database sessions.

Note: JWT-based authentication has been removed in v0.3.0.
Use session-based authentication from src.core.session_dependencies instead.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session


async def get_db() -> AsyncGenerator[AsyncSession]:
    """
    Dependency to get database session.

    The session comes from ``get_db_session``, entered as a context manager so
    that what ends the route reaches it: FastAPI throws a route's exception into
    this generator, and the context manager throws it on into the session
    helper — its rollback, its metric and its log. Delegating with ``async for``
    forwarded nothing (measured 2026-10-25): the rollback branch ran for no
    route, and the session closed only when the garbage collector finalized the
    abandoned generator.

    Yields:
        AsyncSession: SQLAlchemy async database session

    Example:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with asynccontextmanager(get_db_session)() as session:
        yield session
