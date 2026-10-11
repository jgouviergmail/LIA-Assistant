"""Accounted generation reads first and locks only after the provider has returned."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


class PersonalMCPDescriptionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    domain_description: str = Field(min_length=1, max_length=500)
    tool_count: StrictInt = Field(ge=1)


class PersonalMCPDescriptionWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        *,
        expected: PersonalMCPStateSnapshot,
        read_check: PersonalMCPWriteCheck,
        write_check: PersonalMCPWriteCheck,
    ) -> PersonalMCPDescriptionResult: ...
