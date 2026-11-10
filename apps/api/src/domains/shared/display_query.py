"""Validated optional display criteria shared by native, read-only list routes."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from src.core.constants import DISPLAY_SEARCH_MAX_LENGTH

DisplaySort = Literal["recent", "oldest", "name"]


class DisplayQuery(BaseModel):
    """Literal text and display ordering, independent of each source's ownership."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    q: str = Field(
        default="", max_length=DISPLAY_SEARCH_MAX_LENGTH, description="Literal displayed text"
    )
    sort: DisplaySort | None = Field(
        default=None, description="Absent preserves the source's historical order"
    )
    as_of: AwareDatetime | None = Field(
        default=None, description="Upper creation instant; not a historical snapshot"
    )


def display_query(
    q: Annotated[str, Query(max_length=DISPLAY_SEARCH_MAX_LENGTH)] = "",
    sort: Annotated[DisplaySort | None, Query()] = None,
    as_of: Annotated[AwareDatetime | None, Query()] = None,
) -> DisplayQuery:
    """Bind HTTP criteria and a server-owned upper instant for subsequent pages."""
    now = datetime.now(UTC)
    return DisplayQuery(q=q, sort=sort, as_of=min(as_of or now, now))
