"""Message bookmarks configuration (ADR-282).

Contains settings for:
- The deployment ceiling of the bookmarks capability (``PlatformCapability.BOOKMARKS``)
- The number of bookmarks one account may keep

Created: 2026-09-12
Reference: docs/technical/BOOKMARKS.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import BOOKMARKS_MAX_PER_USER_DEFAULT


class BookmarksSettings(BaseSettings):
    """Settings for the answers a person keeps out of their conversations."""

    bookmarks_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling for message bookmarks (PlatformCapability.BOOKMARKS): "
            "the routes, the bubble action and the « Bookmarks » tab."
        ),
    )

    bookmarks_max_per_user: int = Field(
        default=BOOKMARKS_MAX_PER_USER_DEFAULT,
        ge=1,
        le=10_000,
        description=(
            "How many bookmarks one account may keep. Published by the listing and "
            "enforced on creation."
        ),
    )
