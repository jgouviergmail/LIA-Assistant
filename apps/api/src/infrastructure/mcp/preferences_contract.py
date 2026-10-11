"""Typed shared-MCP preference boundary between native consumers and its domain owner."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.preference_cas import PreferenceWriteReceipt

_REFUSALS: TypeAdapter[list[str]] = TypeAdapter(list[str])


def saved_shared_mcp_refusals(value: object) -> list[str]:
    """Only legacy SQL NULL means no opt-outs; malformed JSON never grants access."""
    return _REFUSALS.validate_python([] if value is None else value, strict=True)


class SharedMCPPreferenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_key: str
    name: str
    enabled_for_user: StrictBool
    tools_count: int
    catalogue_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SharedMCPPreferenceReader(Protocol):
    async def __call__(
        self, db: AsyncSession, actor_id: UUID, server_key: str | None = None
    ) -> list[SharedMCPPreferenceSnapshot]: ...


class SharedMCPPreferenceWriter(Protocol):
    async def __call__(
        self,
        db: AsyncSession,
        actor_id: UUID,
        server_key: str,
        enabled: bool,
        *,
        expected: SharedMCPPreferenceSnapshot | None = None,
        receipt: PreferenceWriteReceipt | None = None,
    ) -> SharedMCPPreferenceSnapshot: ...
