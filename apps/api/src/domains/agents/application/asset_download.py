"""Prepare exact browser consent without moving file bytes into the chat."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadInput,
    AssetDownloadPatch,
)
from src.domains.agents.application.asset_download_snapshot import open_asset_snapshot
from src.domains.agents.application.asset_download_spec import ASSET_DOWNLOAD_OPERATION
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.context.runtime_context import runtime_context_if_running


async def prepare_asset_download(
    db: AsyncSession, actor_id: UUID, request: AssetDownloadInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    selected, reader = await open_asset_snapshot(db, actor_id, request)
    await reader.close()
    await authorize_management_export(db, actor_id, context.application_origin)
    return build_action_content(
        actor_id,
        ASSET_DOWNLOAD_OPERATION,
        AssetDownloadPatch(asset_to_download=selected),
        {"asset_to_download": None},
        {"asset_to_download": selected.public_scope()},
        command_id=command_id,
    )
