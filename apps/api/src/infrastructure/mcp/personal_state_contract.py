"""Typed personal switch boundary keeps sealed row witnesses outside public previews."""

from collections.abc import Awaitable, Callable
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mcp.personal_metadata_contract import PersonalMCPReadItem

PersonalMCPWriteCheck = Callable[[AsyncSession], Awaitable[None]]


class PersonalMCPStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server: PersonalMCPReadItem
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PersonalMCPStateReader(Protocol):
    async def __call__(
        self, db: AsyncSession, owner_id: UUID, server_id: UUID
    ) -> PersonalMCPStateSnapshot: ...


class PersonalMCPStateWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        enabled: bool,
        *,
        expected: PersonalMCPStateSnapshot,
        check: PersonalMCPWriteCheck,
    ) -> bool: ...


class PersonalMCPDeleteWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        *,
        expected: PersonalMCPStateSnapshot,
        check: PersonalMCPWriteCheck,
    ) -> bool: ...


class PersonalMCPOAuthDisconnectWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        *,
        expected: PersonalMCPStateSnapshot,
        check: PersonalMCPWriteCheck,
    ) -> bool: ...
