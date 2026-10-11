"""Only browser continuations pass private values through the typed owner port."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mcp.personal_metadata_contract import PersonalMCPReadItem
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


class PersonalMCPConfigurationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server: PersonalMCPReadItem
    changed: StrictBool


class PersonalMCPConfigurationWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        *,
        server_id: UUID | None,
        expected: PersonalMCPStateSnapshot | None,
        values: dict[str, JsonValue],
        read_check: PersonalMCPWriteCheck,
        write_check: PersonalMCPWriteCheck,
    ) -> PersonalMCPConfigurationResult: ...
