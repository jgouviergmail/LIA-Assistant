"""Approved retention shares existing quota serialization and one known SQL commit."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.asset_retention_schemas import (
    AssetRetentionInput,
    AssetRetentionPatch,
    AssetRetentionSelection,
    canonical_asset_retention,
)
from src.domains.agents.application.asset_retention_scope import asset_retention_selection
from src.domains.agents.application.asset_retention_spec import ASSET_RETENTION_OPERATION
from src.domains.agents.application.authorization import authorize_actor, load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.attachments.keep import (
    GeneratedAssetKeepLimitError,
    keep_generated,
    lock_generated_keep_owner,
    release_generated,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)


async def prepare_asset_retention(
    db: AsyncSession,
    actor_id: UUID,
    request: AssetRetentionInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected_request = AssetRetentionInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    selected = await asset_retention_selection(db, actor_id, selected_request)
    _check_retention_capacity(selected)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        ASSET_RETENTION_OPERATION,
        AssetRetentionPatch(asset_retention=selected),
        {"asset_retention": selected.public_scope()},
        {"asset_retention": selected.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_asset_retention(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != ASSET_RETENTION_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_asset_retention(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = AssetRetentionPatch.model_validate(draft.intent).asset_retention

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    actor = authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))
    await lock_generated_keep_owner(db, actor_id)
    if await asset_retention_selection(db, actor_id, selected.request, lock=True) != selected:
        raise CommandRejected("STALE_STATE")
    await check()
    try:
        if selected.request.kept:
            updated, skipped = await keep_generated(
                db, actor_id, list(selected.request.ids), language=actor.language, commit=False
            )
        else:
            updated, skipped = await release_generated(
                db, actor_id, list(selected.request.ids), commit=False
            )
    except GeneratedAssetKeepLimitError as error:
        raise CommandRejected("CONSTRAINT_VIOLATION") from error
    observed = await asset_retention_selection(db, actor_id, selected.request)
    _verify_retention_result(selected, observed, updated, skipped)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.no_op = not selected.changed_items
    receipt.values = {
        "asset_retention": {
            **observed.public_scope(after=True),
            "items": [item.model_dump(mode="json") for item in observed.items],
        }
    }


def _check_retention_capacity(selected: AssetRetentionSelection) -> None:
    desired = selected.desired_usage
    if (
        selected.request.kept
        and selected.changed_items
        and (desired.kept_files > desired.max_files or desired.kept_bytes > desired.max_bytes)
    ):
        raise CommandRejected("CONSTRAINT_VIOLATION")


def _verify_retention_result(
    selected: AssetRetentionSelection,
    observed: AssetRetentionSelection,
    updated: list[UUID],
    skipped: list[UUID],
) -> None:
    expected_updates = (
        list(selected.request.ids)
        if selected.request.kept
        else [item.id for item in selected.changed_items]
    )
    expected_skips = (
        []
        if selected.request.kept
        else [item.id for item in selected.items if item.expires_at is not None]
    )
    if updated != expected_updates or skipped != expected_skips:
        raise CommandRejected("STALE_STATE")
    if observed.ttl_hours != selected.ttl_hours or observed.usage != selected.desired_usage:
        raise CommandRejected("STALE_STATE")
    if any((item.expires_at is None) is not selected.request.kept for item in observed.items):
        raise CommandRejected("STALE_STATE")
    if selected.public_scope(after=True)["items"] != observed.public_scope(after=True)["items"]:
        raise CommandRejected("STALE_STATE")
