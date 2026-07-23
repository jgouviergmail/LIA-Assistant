"""Repository for TOTP secrets and MFA backup codes (security program D1)."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.auth.models import MFABackupCode, UserTOTP


class TOTPRepository(BaseRepository[UserTOTP]):
    """Data access for ``user_totp`` and ``mfa_backup_codes``."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async session.

        Args:
            db: SQLAlchemy async session.
        """
        super().__init__(db, UserTOTP)

    async def get_for_user(self, user_id: UUID) -> UserTOTP | None:
        """Load the user's TOTP row (confirmed or draft).

        Args:
            user_id: Owner UUID.

        Returns:
            The row, or None when the user has no TOTP enrollment.
        """
        result = await self.db.execute(select(UserTOTP).where(UserTOTP.user_id == user_id))
        return result.scalar_one_or_none()

    async def delete_for_user(self, user_id: UUID) -> None:
        """Delete the user's TOTP row (draft replacement or disable).

        Args:
            user_id: Owner UUID.
        """
        await self.db.execute(delete(UserTOTP).where(UserTOTP.user_id == user_id))

    async def delete_codes_for_user(self, user_id: UUID) -> None:
        """Delete every backup code of the user (regenerate or disable).

        Args:
            user_id: Owner UUID.
        """
        await self.db.execute(delete(MFABackupCode).where(MFABackupCode.user_id == user_id))

    async def get_unused_code_by_hash(self, user_id: UUID, code_hash: str) -> MFABackupCode | None:
        """Look up an unused backup code by hash, scoped to its owner.

        Args:
            user_id: Owner UUID.
            code_hash: SHA-256 hex digest of the submitted code.

        Returns:
            The unused code row, or None.
        """
        result = await self.db.execute(
            select(MFABackupCode).where(
                MFABackupCode.user_id == user_id,
                MFABackupCode.code_hash == code_hash,
                MFABackupCode.used_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def count_unused_codes(self, user_id: UUID) -> int:
        """Count the user's remaining unused backup codes.

        Args:
            user_id: Owner UUID.

        Returns:
            Number of unused codes.
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(MFABackupCode)
            .where(
                MFABackupCode.user_id == user_id,
                MFABackupCode.used_at.is_(None),
            )
        )
        return int(result.scalar_one())
