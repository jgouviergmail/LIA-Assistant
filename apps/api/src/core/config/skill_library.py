"""The skill library: skills found on a portal, installed from their origin (ADR-327).

Contains settings for:
- The deployment ceiling of the capability (``PlatformCapability.SKILL_LIBRARY``)
- The portal searched and the audit service read (skills.sh by default)
- The audit risk that refuses an install
- An optional GitHub token, which lifts the anonymous 60 requests per hour
- The bounds of one outgoing request, the cache and the per-account rate limit

Created: 2026-09-30
Reference: docs/architecture/ADR-327-Skill-Library-And-Third-Party-Skills.md
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    SKILL_LIBRARY_AUDIT_BLOCK_LEVEL_DEFAULT,
    SKILL_LIBRARY_AUDIT_URL_DEFAULT,
    SKILL_LIBRARY_CACHE_TTL_SECONDS_DEFAULT,
    SKILL_LIBRARY_PORTAL_URL_DEFAULT,
    SKILL_LIBRARY_RATE_LIMIT_CALLS_DEFAULT,
    SKILL_LIBRARY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    SKILL_LIBRARY_SEARCH_LIMIT_DEFAULT,
    SKILL_LIBRARY_TIMEOUT_SECONDS_DEFAULT,
)

#: An audit verdict, least to most severe (``none`` never refuses).
AuditBlockLevel = Literal["none", "low", "medium", "high", "critical"]


class SkillLibrarySettings(BaseSettings):
    """Settings for searching, installing and updating skills from a portal."""

    skill_library_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling for the skill library (PlatformCapability.SKILL_LIBRARY): "
            "searching a portal, installing a skill from its repository, updating it. "
            "Needs SKILLS_ENABLED."
        ),
    )

    skill_library_portal_url: str = Field(
        default=SKILL_LIBRARY_PORTAL_URL_DEFAULT,
        description="The skills.sh portal searched (https; its /api/search route).",
    )

    skill_library_audit_url: str = Field(
        default=SKILL_LIBRARY_AUDIT_URL_DEFAULT,
        description=(
            "The audit service read before an install (the one the skills CLI reads). "
            "Empty: no audit is read, and nothing is refused on an audit."
        ),
    )

    skill_library_audit_block_level: AuditBlockLevel = Field(
        default=SKILL_LIBRARY_AUDIT_BLOCK_LEVEL_DEFAULT,  # type: ignore[arg-type]
        description=(
            "The audit risk at and above which an install or an update is refused "
            "(none, low, medium, high, critical). `none` shows the audits and refuses "
            "nothing."
        ),
    )

    skill_library_github_token: str | None = Field(
        default=None,
        description=(
            "Optional GitHub token (no scope needed for public repositories). Without "
            "it GitHub allows 60 API requests per hour to the whole instance; with it, "
            "5,000. Sent to api.github.com only."
        ),
    )

    skill_library_search_limit: int = Field(
        default=SKILL_LIBRARY_SEARCH_LIMIT_DEFAULT,
        ge=1,
        le=100,
        description="Results one search asks the portal for.",
    )

    skill_library_timeout_seconds: int = Field(
        default=SKILL_LIBRARY_TIMEOUT_SECONDS_DEFAULT,
        ge=1,
        le=120,
        description="Total deadline of one outgoing request, redirects included (seconds).",
    )

    skill_library_cache_ttl_seconds: int = Field(
        default=SKILL_LIBRARY_CACHE_TTL_SECONDS_DEFAULT,
        ge=0,
        le=86_400,
        description=(
            "How long a search answer and a branch head are reused (seconds). 0 reads "
            "them afresh every time."
        ),
    )

    skill_library_rate_limit_calls: int = Field(
        default=SKILL_LIBRARY_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Calls one account may make per window to the routes that reach the network.",
    )

    skill_library_rate_limit_window_seconds: int = Field(
        default=SKILL_LIBRARY_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=86_400,
        description="The sliding window of the per-account limit (seconds).",
    )
