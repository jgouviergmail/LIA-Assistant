"""What the rail reads: each tool's state, its provider's gestures, the bounds (ADR-369)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domains.workbench.features import WorkbenchFeature, WorkbenchTool

ToolState = Literal["ready", "not_connected", "reconnect_required", "unavailable"]


class ToolAvailability(BaseModel):
    """One tool of the rail."""

    model_config = ConfigDict(frozen=True)

    tool: WorkbenchTool = Field(description="The tool.")
    state: ToolState = Field(
        description=(
            "ready — usable; reconnect_required — its provider broke and needs a new "
            "authorisation; not_connected — connect a provider in Settings › Connectors; "
            "unavailable — the instance offers no provider for it."
        )
    )
    provider: str | None = Field(
        description="The connector type serving it (also when it must be reconnected)."
    )
    features: list[WorkbenchFeature] = Field(
        description="The gestures this provider accepts (empty when not usable)."
    )
    bounds: dict[str, int] = Field(
        description="Numeric limits this provider imposes, published because enforced."
    )


class WorkbenchLimits(BaseModel):
    """The bounds every workbench route enforces, published (ADR-184)."""

    model_config = ConfigDict(frozen=True)

    page_size: int = Field(description="Items in one page of a listing.")
    bulk_max_items: int = Field(description="The largest selection one bulk act carries.")
    upload_max_bytes: int = Field(description="The largest file sent to a drive (bytes).")
    download_max_bytes: int = Field(description="The largest file served, in bytes.")
    calendar_window_max_events: int = Field(
        description="Events read per calendar and window; past it the view says it is cut."
    )
    send_undo_seconds: int = Field(
        description="How long « Send » waits on the page before a message leaves (0: at once)."
    )
    draft_autosave_seconds: int = Field(
        description="How long a composer stays quiet before it saves a draft (0: never by itself)."
    )
    search_max_chars: int = Field(description="The longest words one search takes.")


class WorkbenchAvailability(BaseModel):
    """The rail: every tool in rail order, and the bounds."""

    model_config = ConfigDict(frozen=True)

    tools: list[ToolAvailability] = Field(description="The six tools, in rail order.")
    limits: WorkbenchLimits = Field(description="The bounds every route enforces.")
