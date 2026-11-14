"""Native account cleanup is composed by infrastructure, not imported by users."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class AccountCleanupPort(Protocol):
    """Actual cleanup operations, each owning short sessions around its I/O."""

    async def cleanup_page(self, sessions: async_sessionmaker[AsyncSession], owner: UUID) -> int:
        """Attempt bounded runtime/file work and return explicitly removed file count."""
        ...

    async def purge_store(self, owner: UUID) -> int:
        """Remove exact account namespaces through the native Store API."""
        ...


_cleanup: AccountCleanupPort | None = None


def configure_account_cleanup(port: AccountCleanupPort | None) -> None:
    """Install at startup or withdraw during isolated composition tests."""
    global _cleanup
    _cleanup = port


def account_cleanup() -> AccountCleanupPort:
    """Refuse unconfigured cleanup before retiring personal data."""
    if _cleanup is None:
        raise RuntimeError("Account cleanup was not configured at startup")
    return _cleanup
