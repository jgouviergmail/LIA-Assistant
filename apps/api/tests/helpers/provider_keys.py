"""Synthetic provider credentials scoped to a disposable integration database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.security.utils import encrypt_data
from src.domains.llm_config.models import ProviderApiKey


@asynccontextmanager
async def provider_key_scope(
    maker: async_sessionmaker[AsyncSession], *, provider: str, key: str
) -> AsyncIterator[None]:
    """Restore the prior row after tests which commit through independent sessions."""
    async with maker() as db:
        prior = await db.scalar(select(ProviderApiKey).where(ProviderApiKey.provider == provider))
        saved = (
            {
                column.name: getattr(prior, column.name)
                for column in ProviderApiKey.__table__.columns
            }
            if prior
            else None
        )
        if prior is not None:
            prior.encrypted_key = encrypt_data(key)
            prior.updated_by = None
        else:
            db.add(ProviderApiKey(provider=provider, encrypted_key=encrypt_data(key)))
        await db.commit()
    try:
        yield
    finally:
        async with maker() as db:
            await db.execute(delete(ProviderApiKey).where(ProviderApiKey.provider == provider))
            if saved is not None:
                db.add(ProviderApiKey(**saved))
            await db.commit()
