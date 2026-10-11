"""Only existing non-secret form settings can enter model arguments."""

from typing import Protocol
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)


class PersonalMCPSettingsValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    domain_description: str | None = Field(default=None, max_length=500)
    timeout_seconds: StrictInt | None = Field(default=None, ge=5, le=120)
    iterative_mode: StrictBool | None = None

    @field_validator("name")
    @classmethod
    def require_visible_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("MCP server name cannot be blank")
        return value

    @model_validator(mode="after")
    def require_actual_supported_values(self) -> PersonalMCPSettingsValues:
        if not self.model_fields_set:
            raise ValueError("At least one MCP setting is required")
        if any(
            getattr(self, name) is None for name in self.model_fields_set - {"domain_description"}
        ):
            raise ValueError("Only the description may be cleared")
        return self


class PersonalMCPSettingsWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        owner_id: UUID,
        server_id: UUID,
        patch: PersonalMCPSettingsValues,
        *,
        expected: PersonalMCPStateSnapshot,
        check: PersonalMCPWriteCheck,
    ) -> bool: ...
