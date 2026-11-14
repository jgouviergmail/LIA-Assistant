"""Typed probe outcome exposes safe stored metadata, never raw transport errors."""

from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mcp.personal_metadata_contract import PersonalMCPReadItem
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


class PersonalMCPConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    success: StrictBool
    server: PersonalMCPReadItem
    # ``authorization_required``: an OAuth server holds no usable token, so the remedy the
    # assistant offers is the authorization card, not another probe.
    error: Literal["connection_failed", "authorization_required"] | None


class PersonalMCPConnectionWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        *,
        expected: PersonalMCPStateSnapshot,
        read_check: PersonalMCPWriteCheck,
        write_check: PersonalMCPWriteCheck,
    ) -> PersonalMCPConnectionResult: ...
