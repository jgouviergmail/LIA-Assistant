"""Effect-free proposals for one current owned channel identity."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.channel_schemas import (
    ChannelBindingUnlinkPatch,
    ChannelBindingUnlinkRequest,
    ChannelBindingUpdatePatch,
    ChannelBindingUpdateRequest,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.preparation import _preference_content
from src.domains.channels.models import UserChannelBinding
from src.domains.channels.preference_commands import (
    ChannelBindingSnapshot,
    channel_binding_snapshot,
)
from src.domains.channels.read_projection import channel_bindings_response
from src.domains.channels.repository import UserChannelBindingRepository
from src.domains.channels.schemas import ChannelBindingListResponse
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability


async def read_channel_bindings(db: AsyncSession, actor_id: UUID) -> ChannelBindingListResponse:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.CHANNELS)
    await load_actor(db, actor_id)
    return channel_bindings_response(
        await UserChannelBindingRepository(db).get_all_for_user(actor_id)
    )


async def prepare_channel_binding_content(
    db: AsyncSession,
    actor_id: UUID,
    request: ChannelBindingUpdateRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    before = await _owned_binding_snapshot(db, actor_id, request.binding_id)
    desired = before.model_copy(update={"is_active": request.enabled})
    return _preference_content(
        actor_id,
        ChannelBindingUpdatePatch(channel_binding=desired),
        {"channel_binding": before.model_dump(mode="json")},
        command_id=command_id,
    )


async def prepare_channel_unlink_content(
    db: AsyncSession,
    actor_id: UUID,
    request: ChannelBindingUnlinkRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    before = await _owned_binding_snapshot(db, actor_id, request.binding_id)
    return _preference_content(
        actor_id,
        ChannelBindingUnlinkPatch(channel_binding=before),
        {"channel_binding": before.model_dump(mode="json")},
        command_id=command_id,
    )


async def _owned_binding_snapshot(
    db: AsyncSession, actor_id: UUID, binding_id: UUID
) -> ChannelBindingSnapshot:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.CHANNELS)
    await load_actor(db, actor_id)
    binding: UserChannelBinding | None = await db.scalar(
        select(UserChannelBinding)
        .where(UserChannelBinding.id == binding_id, UserChannelBinding.user_id == actor_id)
        .execution_options(populate_existing=True)
    )
    if binding is None or binding.id != binding_id or binding.user_id != actor_id:
        raise ResourceNotFoundError("channel_binding", str(binding_id))
    return channel_binding_snapshot(binding)
