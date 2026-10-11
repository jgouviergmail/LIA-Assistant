"""Portable, bounded current-account meeting and template observations."""

from datetime import datetime
from typing import Literal, Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictInt, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.exceptions import AuthorizationError

MeetingReadView = Literal[
    "list",
    "active",
    "limits",
    "detail",
    "report",
    "generated_report",
    "transcript",
    "template_snapshot",
]
TemplateReadView = Literal["library", "template"]
CONTENT_VIEWS = frozenset({"report", "generated_report", "transcript", "template_snapshot"})
MEETING_READ_MAX_BYTES = 64_000


class MeetingReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: MeetingReadView = "list"
    meeting_id: UUID | None = None
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=25, ge=1, le=100)
    characters: StrictInt = Field(default=4000, ge=100, le=8000)
    expected_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        needs_id = self.view not in {"list", "active", "limits"}
        if needs_id != (self.meeting_id is not None):
            raise ValueError("This view requires exactly its owned meeting identifier")
        if self.view in {"active", "limits"} and self.offset:
            raise ValueError("This view is not paginated")
        if self.view not in CONTENT_VIEWS and self.expected_digest is not None:
            raise ValueError("Only content pages accept a source digest")
        if self.view in CONTENT_VIEWS and self.offset and self.expected_digest is None:
            raise ValueError("Continue content only with the first page's source digest")
        if self.view == "detail" and self.offset:
            raise ValueError("Detail metadata is not paginated")
        return self


class TemplateReadInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: TemplateReadView = "library"
    ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-fA-F-]{36})$",
    )
    offset: StrictInt = Field(default=0, ge=0)
    limit: StrictInt = Field(default=25, ge=1, le=100)
    characters: StrictInt = Field(default=4000, ge=100, le=8000)
    expected_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exact_selection(self) -> Self:
        if (self.view == "template") != (self.ref is not None):
            raise ValueError("Template detail requires one exact reference")
        if self.view == "template" and self.offset and self.expected_digest is None:
            raise ValueError("Continue template content with its source digest")
        if self.view == "library" and self.expected_digest is not None:
            raise ValueError("Library item pagination is live")
        return self


class MeetingReadPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    view: MeetingReadView | TemplateReadView
    observed_at: datetime
    data: dict[str, JsonValue] = Field(default_factory=dict)
    total: StrictInt = Field(ge=0)
    offset: StrictInt = Field(ge=0)
    next_offset: StrictInt | None = Field(default=None, ge=0)
    text: str | None = None
    source_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    content_format: Literal["json_fragment"] | None = None


class MeetingReadGateway(Protocol):
    async def meetings(
        self, db: AsyncSession, actor_id: UUID, query: MeetingReadInput
    ) -> MeetingReadPage: ...
    async def templates(
        self, db: AsyncSession, actor_id: UUID, query: TemplateReadInput, language: str | None
    ) -> MeetingReadPage: ...


_gateway: MeetingReadGateway | None = None


def configure_meeting_reads(gateway: MeetingReadGateway | None) -> MeetingReadGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_meeting_reads() -> MeetingReadGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
