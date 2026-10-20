"""Stable tenant HMAC material, wrapped independently of its hash identities.

Creation requires the caller's owner lock. Rewrapping this column during Fernet
rotation preserves opaque receipts, sender blocks and search terms. Missing or
unreadable established material fails closed; it is never regenerated silently.
"""

import secrets

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ExternalServiceError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.ingestion.models import IngestionSource
from src.domains.ingestion.registry import IngestionResource, policy_for
from src.domains.users.models import User
from src.infrastructure.database.session import Base


def key_for_owner(owner: User) -> bytes:
    if owner.ingestion_key_encrypted is None:
        raise ExternalServiceError("ingestion", detail="ingestion_key_unavailable")
    try:
        version, encoded = decrypt_data(owner.ingestion_key_encrypted).split(":", 1)
        if version != "v1":
            raise ValueError("unsupported_ingestion_key_format")
        key = bytes.fromhex(encoded)
    except ValueError:
        raise ExternalServiceError("ingestion", detail="ingestion_key_unavailable") from None
    if len(key) != 32:
        raise ExternalServiceError("ingestion", detail="ingestion_key_unavailable")
    return key


async def initialize_owner_key(db: AsyncSession, owner: User) -> bytes:
    if owner.ingestion_key_encrypted is not None:
        return key_for_owner(owner)
    established = await db.scalar(select(exists().where(IngestionSource.user_id == owner.id)))
    for resource in IngestionResource:
        for table_name in policy_for(resource).keyed_state_tables:
            table = Base.metadata.tables[table_name]
            established = established or await db.scalar(
                select(exists().where(table.c.user_id == owner.id))
            )
    if established:
        raise ExternalServiceError("ingestion", detail="ingestion_key_unavailable")
    owner.ingestion_key_encrypted = encrypt_data("v1:" + secrets.token_hex(32))
    return key_for_owner(owner)
