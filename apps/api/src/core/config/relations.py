"""Relations (personal CRM) configuration module (N-09).

Env-overridable caps for the read-only relationship aggregation. Defaults are
imported from ``src.core.constants`` (not from the relations domain: importing
it here would wire its router and create a config↔domain cycle — same rule as
``config/briefing.py``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    RELATIONS_MAX_ITEMS_DEFAULT,
    RELATIONS_MAX_ITEMS_PER_SECTION_DEFAULT,
)


class RelationsSettings(BaseSettings):
    """Env-overridable caps for the personal-CRM aggregation."""

    relations_max_items: int = Field(
        default=RELATIONS_MAX_ITEMS_DEFAULT,
        ge=1,
        le=200,
        description="Maximum relationships listed on the CRM overview.",
    )
    relations_max_items_per_section: int = Field(
        default=RELATIONS_MAX_ITEMS_PER_SECTION_DEFAULT,
        ge=1,
        le=50,
        description="Maximum open loops / calls / memories per relationship.",
    )
