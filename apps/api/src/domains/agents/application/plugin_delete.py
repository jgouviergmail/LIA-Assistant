"""Complete original group/row/files state is checked under ownership locks before removal."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_delete_schemas import (
    PluginDeleteInput,
    PluginDeletePatch,
    PluginDeleteSnapshot,
    canonical_plugin_deletion,
)
from src.domains.agents.application.plugin_delete_spec import PLUGIN_DELETE_OPERATION
from src.domains.agents.application.plugin_read import require_plugin_access
from src.domains.agents.application.plugin_state import plugin_group_witness, plugin_public_item
from src.domains.plugins.group_scope import PluginGroup, load_plugin_group
from src.domains.plugins.removal import PluginRemovalCompletionUnknown, remove_plugin
from src.domains.plugins.removal_disk import RemovalMove
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _snapshot(group: PluginGroup, owner_id: UUID) -> PluginDeleteSnapshot:
    row = group.plugin
    return PluginDeleteSnapshot(
        request=PluginDeleteInput(plugin_id=row.id),
        plugin=plugin_public_item(group),
        state_digest=await asyncio.to_thread(plugin_group_witness, group, owner_id),
    )


async def prepare_plugin_deletion(
    db: AsyncSession, actor_id: UUID, request: PluginDeleteInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = PluginDeleteInput.model_validate(request.model_dump())
    await require_plugin_access(db, actor_id)
    selected = await _snapshot(await load_plugin_group(db, actor_id, desired.plugin_id), actor_id)
    await require_plugin_access(db, actor_id)
    return build_action_content(
        actor_id,
        PLUGIN_DELETE_OPERATION,
        PluginDeletePatch(plugin_to_delete=selected),
        {"plugin_to_delete": selected.public_scope()},
        {"plugin_to_delete": None},
        command_id=command_id,
    )


async def execute_plugin_deletion(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != PLUGIN_DELETE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_plugin_deletion(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = PluginDeletePatch.model_validate(draft.intent).plugin_to_delete
    approved_group: PluginGroup | None = None
    staged: tuple[RemovalMove, ...] = ()

    async def before_stage(group: PluginGroup) -> None:
        nonlocal approved_group
        await require_plugin_access(db, actor_id)
        if await _snapshot(group, actor_id) != expected:
            raise CommandRejected("STALE_STATE")
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        approved_group = group

    async def after_stage(moves: tuple[RemovalMove, ...]) -> None:
        nonlocal staged
        staged = moves

    async def before_commit() -> None:
        await require_plugin_access(db, actor_id)
        if (
            approved_group is None
            or await asyncio.to_thread(plugin_group_witness, approved_group, actor_id, staged)
            != expected.state_digest
        ):
            raise CommandRejected("STALE_STATE")
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    def committed() -> None:
        receipt.committed = True
        receipt.values = {
            "plugin_to_delete": None,
            "file_cleanup_pending": True,
            "pool_cleanup_pending": True,
            "cache_refresh_pending": True,
        }

    try:
        result = await remove_plugin(
            db,
            actor_id,
            expected.request.plugin_id,
            before_stage=before_stage,
            after_stage=after_stage,
            before_commit=before_commit,
            after_commit=committed,
        )
    except PluginRemovalCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.values = {
        "plugin_to_delete": None,
        "file_cleanup_pending": result.file_cleanup_pending,
        "pool_cleanup_pending": result.pool_cleanup_pending,
        "cache_refresh_pending": result.cache_refresh_pending,
    }
