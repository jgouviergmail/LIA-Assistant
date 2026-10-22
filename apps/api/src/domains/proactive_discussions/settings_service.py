"""Native personal preference commands; assistant writes wrap these in the common HITL gate."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.proactive_discussions.api_schemas import (
    DiscussionSettingsResponse,
    DiscussionSettingsUpdate,
    SourceOption,
)
from src.domains.proactive_discussions.policy_repository import DiscussionPolicyRepository
from src.domains.proactive_discussions.registry import SOURCE_REGISTRY
from src.domains.proactive_discussions.schemas import DiscussionPolicy


def settings_response(
    policy: DiscussionPolicy, *, producer_enabled: bool | None = None
) -> DiscussionSettingsResponse:
    """Build the settings payload: the policy, the source catalogue, availability.

    Args:
        policy: The account's policy.
        producer_enabled: Whether the producer may run, when already known;
            otherwise the instance setting.

    Returns:
        The settings response, stating whether the three spending limits are set.
    """
    return DiscussionSettingsResponse(
        policy=policy,
        sources=tuple(
            SourceOption(
                key=key,
                operations=value.operations,
                indivisible=value.indivisible,
                dependencies=value.dependencies,
            )
            for key, value in SOURCE_REGISTRY.items()
        ),
        producer_enabled=(
            settings.proactive_discussions_enabled if producer_enabled is None else producer_enabled
        ),
        budget_configured=all(
            value is not None
            for value in (
                settings.discussion_owner_daily_budget_usd,
                settings.discussion_instance_daily_budget_usd,
                settings.discussion_run_budget_usd,
            )
        ),
        pause_hours=settings.discussion_pause_hours,
    )


async def read_settings(db: AsyncSession, owner_id: UUID) -> DiscussionSettingsResponse:
    """Read the account's discussion settings.

    Args:
        db: The session to read with.
        owner_id: The account.

    Returns:
        The settings response, with the operator's switch read fresh.
    """
    return settings_response(
        await DiscussionPolicyRepository(db).get_policy(owner_id),
        producer_enabled=await producer_available(db),
    )


async def update_settings(
    db: AsyncSession, owner_id: UUID, data: DiscussionSettingsUpdate
) -> DiscussionSettingsResponse:
    """Apply a settings change and return the settings after it.

    Args:
        db: The session to write with.
        owner_id: The account.
        data: The change and the revision it was made against.

    Returns:
        The settings after the change.

    Raises:
        ResourceConflictError: The policy changed since the expected revision.
    """
    policy = await DiscussionPolicyRepository(db).update_policy(
        owner_id, data.changes, expected_revision=data.expected_revision
    )
    return settings_response(policy, producer_enabled=await producer_available(db))


async def producer_available(db: AsyncSession) -> bool:
    """Whether the operator's switch for proactive discussions is on, read fresh.

    Args:
        db: The session to read with.

    Returns:
        False when the capability is switched off.
    """
    try:
        await require_capability_fresh(db, PlatformCapability.PROACTIVE_DISCUSSIONS)
    except AuthorizationError:
        return False
    return True
