"""
Pydantic models for browser automation data.

Phase: evolution F7 — Browser Control (Playwright)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PageSnapshot(BaseModel):
    """Snapshot of a browser page content.

    Can contain either visible text content (from navigate — for content extraction)
    or an accessibility tree with [EN] refs (from snapshot — for interaction).
    """

    url: str = Field(..., description="Current page URL.")
    title: str = Field(..., description="Page title.")
    content: str = Field(
        ..., description="Page content: visible text (navigate) or AX tree with refs (snapshot)."
    )
    interactive_count: int = Field(default=0, description="Number of interactive elements.")
    total_count: int = Field(default=0, description="Total AX tree nodes before compaction.")


class BrowserAction(BaseModel):
    """Represents a single browser action for logging and metrics."""

    action_type: Literal["navigate", "click", "fill", "press_key", "screenshot", "snapshot"] = (
        Field(..., description="Type of browser action.")
    )
    ref: str | None = Field(default=None, description="Element reference (e.g., 'E3').")
    value: str | None = Field(default=None, description="Value for fill actions.")
    key: str | None = Field(default=None, description="Key name for press_key actions.")


class BrowserSessionInfo(BaseModel):
    """Metadata for a browser session stored in Redis for cross-worker recovery.

    This lightweight model is serialized to Redis with a TTL matching the session timeout.
    When a follow-up request lands on a different worker, it reads this metadata
    and re-navigates to the stored URL transparently.
    """

    session_id: str = Field(..., description="Unique session identifier.")
    user_id: str = Field(..., description="User who owns this session.")
    created_at: datetime = Field(..., description="Session creation timestamp (UTC).")
    current_url: str | None = Field(default=None, description="Last navigated URL.")
    page_title: str | None = Field(default=None, description="Last page title.")
    worker_pid: int = Field(..., description="PID of the worker process owning this session.")
    navigation_count: int = Field(default=0, description="Number of navigations in this session.")
