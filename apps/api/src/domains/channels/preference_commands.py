"""Current-owner channel commands shared by HTTP and confirmed application actions."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError, ResourceNotFoundError, raise_user_not_found
from src.domains.channels.models import ChannelType, UserChannelBinding
from src.domains.channels.schemas import ChannelBindingResponse
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


class ChannelBindingSnapshot(BaseModel):
    """Visible binding identity and state, excluding credentials and derived timestamps."""

    model_config = ConfigDict(extra="forbid", from_attributes=True, frozen=True)
    id: UUID
    channel_type: ChannelType
    channel_user_id: str
    channel_username: str | None
    is_active: StrictBool


def assert_channel_snapshot_coverage() -> None:
    if set(ChannelBindingResponse.model_fields) != set(ChannelBindingSnapshot.model_fields) | {
        "created_at",
        "updated_at",
    }:
        raise AssertionError(
            "New channel binding display fields require explicit command snapshot review"
        )


def channel_binding_snapshot(binding: UserChannelBinding) -> ChannelBindingSnapshot:
    return ChannelBindingSnapshot.model_validate(binding)


async def _locked_owned_binding(
    db: AsyncSession, actor_id: UUID, binding_id: UUID
) -> UserChannelBinding:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise_user_not_found(actor_id)
    binding: UserChannelBinding | None = await db.scalar(
        select(UserChannelBinding)
        .where(UserChannelBinding.id == binding_id, UserChannelBinding.user_id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if binding is None or binding.id != binding_id or binding.user_id != actor_id:
        raise ResourceNotFoundError("channel_binding", str(binding_id))
    return binding


def _check_expected(binding: UserChannelBinding, expected: ChannelBindingSnapshot | None) -> None:
    if expected is not None and channel_binding_snapshot(binding) != expected:
        raise ResourceConflictError("channel_binding", detail={"error_code": "STALE_STATE"})


async def _save_binding_state(
    db: AsyncSession,
    binding: UserChannelBinding,
    desired: bool,
    receipt: PreferenceWriteReceipt | None,
) -> UserChannelBinding:
    if binding.is_active == desired:
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return binding
    binding.is_active = desired
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    await db.refresh(binding)
    return binding


async def set_channel_binding_state(
    db: AsyncSession,
    actor_id: UUID,
    binding_id: UUID,
    desired: bool,
    *,
    expected: ChannelBindingSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> UserChannelBinding:
    binding = await _locked_owned_binding(db, actor_id, binding_id)
    _check_expected(binding, expected)
    return await _save_binding_state(db, binding, desired, receipt)


async def toggle_owned_channel_binding(
    db: AsyncSession, actor_id: UUID, binding_id: UUID
) -> UserChannelBinding:
    binding = await _locked_owned_binding(db, actor_id, binding_id)
    return await _save_binding_state(db, binding, not binding.is_active, None)


async def unlink_owned_channel_binding(
    db: AsyncSession,
    actor_id: UUID,
    binding_id: UUID,
    *,
    expected: ChannelBindingSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> str:
    binding = await _locked_owned_binding(db, actor_id, binding_id)
    _check_expected(binding, expected)
    channel_type = binding.channel_type
    await db.delete(binding)
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return channel_type


assert_channel_snapshot_coverage()
