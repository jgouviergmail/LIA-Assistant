"""Fresh account admission for Fish Audio library writes."""

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import FISHAUDIO_PROVIDER_NAME
from src.domains.llm_config.credential_fence import credential_is_current
from src.domains.voice.fishaudio.library_errors import ACCOUNT_CHANGED, refuse


async def require_current_account(db: AsyncSession, fingerprint: str | None) -> None:
    """Fence the local admission/write against the account actually read or used."""
    if not await credential_is_current(db, FISHAUDIO_PROVIDER_NAME, fingerprint):
        refuse(status.HTTP_409_CONFLICT, ACCOUNT_CHANGED)
