"""Bind an account-dependent result to the credential actually used to obtain it."""

import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.utils import decrypt_data
from src.domains.llm_config.models import ProviderApiKey


def credential_fingerprint(api_key: str) -> str:
    """An internal comparison value, never a public identifier or log field."""
    return hashlib.sha256(api_key.encode()).hexdigest()


async def credential_is_current(db: AsyncSession, provider: str, fingerprint: str | None) -> bool:
    """Compare fresh SQL and hold a shared row lock through the caller's write.

    UPDATE/DELETE of that credential waits until this transaction completes.
    No vendor operation belongs inside this transaction. A worker's cache is
    not an authority here, and absent or unreadable credentials fail closed.
    """
    if fingerprint is None:
        return False
    encrypted = await db.scalar(
        select(ProviderApiKey.encrypted_key)
        .where(ProviderApiKey.provider == provider)
        .with_for_update(read=True)
    )
    if encrypted is None:
        return False
    try:
        key = decrypt_data(encrypted)
    except ValueError:
        return False
    return bool(key) and hmac.compare_digest(credential_fingerprint(key), fingerprint)
