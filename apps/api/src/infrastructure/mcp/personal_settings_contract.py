"""Only existing non-secret form settings can enter model arguments.

Confirmation travels here tighten-only (spec 2026-10-30 D7): the server's confirmation
is published as « true » alone, a tool's choice as the tools to always ask about, and
who drives the server is judged at proposal and at the write by the computation that
alerts the person on the settings page.
"""

from typing import Annotated, Protocol
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import MCP_TOOL_CHOICE_NAME_MAX_LENGTH
from src.infrastructure.mcp.personal_state_contract import (
    PersonalMCPStateSnapshot,
    PersonalMCPWriteCheck,
)

_ToolName = Annotated[
    str, StringConstraints(min_length=1, max_length=MCP_TOOL_CHOICE_NAME_MAX_LENGTH)
]
_LOOSENING_PATH = (
    "From the chat LIA can only make itself ask more; a change that would make it ask "
    "less is refused, and the person makes it in Settings > MCP Servers."
)


class PersonalMCPSettingsValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    domain_description: str | None = Field(default=None, max_length=500)
    timeout_seconds: StrictInt | None = Field(default=None, ge=5, le=120)
    iterative_mode: StrictBool | None = Field(
        default=None,
        description=(
            "true: a dedicated agent drives the server's tools; false: LIA uses them "
            f"directly. {_LOOSENING_PATH}"
        ),
    )
    react_expand_iterative: StrictBool | None = Field(
        default=None,
        description=(
            "For a server driven by a dedicated agent: true lets the ReAct mode use its "
            f"tools directly, false keeps the agent in both modes. {_LOOSENING_PATH}"
        ),
    )
    hitl_required: StrictBool | None = Field(
        default=None,
        description=f"Only true: ask before every call of this server's tools. {_LOOSENING_PATH}",
        json_schema_extra={"const": True},
    )
    always_ask_tools: tuple[_ToolName, ...] | None = Field(
        default=None,
        min_length=1,
        max_length=settings.mcp_max_tools_per_server,
        description=(
            "Tools of this server to always ask about before each call, by the exact "
            f"names its catalogue lists. {_LOOSENING_PATH}"
        ),
        json_schema_extra={"uniqueItems": True},
    )

    @field_validator("name")
    @classmethod
    def require_visible_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("MCP server name cannot be blank")
        return value

    @field_validator("always_ask_tools")
    @classmethod
    def require_distinct_tools(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("Name each tool once")
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


class PersonalMCPSettingsJudge(Protocol):
    """Refuses, before a card is proposed, a patch that would make LIA ask less."""

    async def __call__(
        self, db: AsyncSession, owner_id: UUID, server_id: UUID, patch: PersonalMCPSettingsValues
    ) -> None: ...
