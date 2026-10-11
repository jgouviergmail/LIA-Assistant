"""One complete profile projection shared by ordinary and administrative views."""

from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.chat.models import UserStatistics

from src.domains.users.admin_columns import admin_user_switches
from src.domains.users.models import User
from src.domains.users.schemas import HomeLocationData, UserProfile, UserProfileWithStats


def build_user_profile(user: User) -> UserProfile:
    """Read every declared field; ORM values must never be replaced by DTO defaults.

    Home address is the one derived field: decode encrypted location separately.
    An unreadable legacy location preserves the existing absent-address fallback.
    """
    home_address = None
    if user.home_location_encrypted:
        with suppress(Exception):
            from src.core.security.utils import decrypt_data

            location_data = HomeLocationData.model_validate_json(
                decrypt_data(user.home_location_encrypted)
            )
            home_address = location_data.address
    profile = UserProfile.model_validate(user)
    return profile.model_copy(update={"home_address": home_address})


def build_user_profile_with_stats(
    base_profile: UserProfile,
    user: User,
    stats: UserStatistics | None,
    active_connectors_count: int = 0,
    last_message_at: datetime | None = None,
    memories_count: int = 0,
    interests_count: int = 0,
    skills_count: int = 0,
    mcp_servers_count: int = 0,
    scheduled_actions_count: int = 0,
    rag_spaces_count: int = 0,
    is_usage_blocked: bool = False,
) -> UserProfileWithStats:
    """
    Build UserProfileWithStats from User and UserStatistics models.

    Args:
        user: User model instance
        stats: UserStatistics model instance (can be None)
        active_connectors_count: Number of active connectors for this user
        last_message_at: Timestamp of last message sent
        memories_count: Number of memories stored for this user
        interests_count: Number of interests for this user
        skills_count: Number of user-imported skills
        mcp_servers_count: Number of user MCP servers
        scheduled_actions_count: Number of scheduled actions
        rag_spaces_count: Number of RAG knowledge spaces
        is_usage_blocked: Whether user is usage-blocked by admin

    Returns:
        UserProfileWithStats with all fields populated
    """
    # Calculate statistics - Lifetime totals
    tokens_in = stats.total_prompt_tokens if stats else 0
    tokens_out = stats.total_completion_tokens if stats else 0
    tokens_cache = stats.total_cached_tokens if stats else 0
    total_tokens = tokens_in + tokens_out + tokens_cache
    total_messages = stats.total_messages if stats else 0
    # Consolidate all costs (LLM + Google API + Image Generation) into totals
    total_cost_eur = (
        (
            float(stats.total_cost_eur)
            + float(getattr(stats, "total_google_api_cost_eur", 0) or 0)
            + float(getattr(stats, "total_image_generation_cost_eur", 0) or 0)
        )
        if stats
        else 0.0
    )
    total_google_api_requests = stats.total_google_api_requests if stats else 0

    # Calculate statistics - Current billing cycle
    cycle_prompt = stats.cycle_prompt_tokens if stats else 0
    cycle_completion = stats.cycle_completion_tokens if stats else 0
    cycle_cache = stats.cycle_cached_tokens if stats else 0
    cycle_tokens = cycle_prompt + cycle_completion + cycle_cache
    cycle_messages = stats.cycle_messages if stats else 0
    cycle_google_api_requests = stats.cycle_google_api_requests if stats else 0
    cycle_cost_eur = (
        (
            float(stats.cycle_cost_eur)
            + float(getattr(stats, "cycle_google_api_cost_eur", 0) or 0)
            + float(getattr(stats, "cycle_image_generation_cost_eur", 0) or 0)
        )
        if stats
        else 0.0
    )

    return UserProfileWithStats(
        # Base profile fields, spread rather than named: the list this
        # replaces had drifted the same way its sibling had, dropping the
        # very preferences the base profile has just been careful to read.
        # The table's switches are merged over it, a few being in both.
        **{**base_profile.model_dump(), **admin_user_switches(user)},
        # Statistics fields - Lifetime totals
        last_login=user.last_login,
        last_message_at=last_message_at,
        total_messages=total_messages,
        total_tokens=total_tokens,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        tokens_cache=tokens_cache,
        total_cost_eur=total_cost_eur,
        total_google_api_requests=total_google_api_requests,
        # Statistics fields - Current billing cycle
        cycle_messages=cycle_messages,
        cycle_tokens=cycle_tokens,
        cycle_google_api_requests=cycle_google_api_requests,
        cycle_cost_eur=cycle_cost_eur,
        # Other stats
        active_connectors_count=active_connectors_count,
        memories_count=memories_count,
        interests_count=interests_count,
        skills_count=skills_count,
        mcp_servers_count=mcp_servers_count,
        scheduled_actions_count=scheduled_actions_count,
        rag_spaces_count=rag_spaces_count,
        is_usage_blocked=is_usage_blocked,
    )
