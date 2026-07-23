"""Repository for WebAuthn passkey credentials (security program D1)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repository import BaseRepository
from src.domains.auth.models import WebAuthnCredential


class WebAuthnCredentialRepository(BaseRepository[WebAuthnCredential]):
    """Data access for the ``webauthn_credentials`` table."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with an async session.

        Args:
            db: SQLAlchemy async session.
        """
        super().__init__(db, WebAuthnCredential)

    async def list_for_user(self, user_id: UUID) -> list[WebAuthnCredential]:
        """List all passkeys registered by a user, oldest first.

        Args:
            user_id: Owner UUID.

        Returns:
            The user's credentials ordered by creation date.
        """
        result = await self.db.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user_id)
            .order_by(WebAuthnCredential.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_credential_id(self, credential_id: str) -> WebAuthnCredential | None:
        """Look up a credential by its base64url WebAuthn credential id.

        Args:
            credential_id: Base64url-encoded credential identifier.

        Returns:
            The credential row, or None when unknown.
        """
        result = await self.db.execute(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, user_id: UUID, row_id: UUID) -> WebAuthnCredential | None:
        """Load one credential row scoped to its owner (ownership enforced in SQL).

        Args:
            user_id: Owner UUID.
            row_id: Credential row UUID (primary key, not the WebAuthn id).

        Returns:
            The credential row, or None when absent or owned by someone else.
        """
        result = await self.db.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.id == row_id,
                WebAuthnCredential.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()
