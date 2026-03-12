"""
FastAPI dependency injection utilities.
Provides common dependencies for database sessions.

Note: JWT-based authentication has been removed in v0.3.0.
Use session-based authentication from src.core.session_dependencies instead.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.session import get_db_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session.

    Yields:
        AsyncSession: SQLAlchemy async database session

    Example:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    async for session in get_db_session():
        yield session
