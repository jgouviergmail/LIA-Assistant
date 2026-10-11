"""Refreshing consent keeps its exact artifact and original pending browser command."""

from src.domains.agents.application.asset_download import prepare_asset_download
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadInput,
    AssetDownloadPatch,
)
from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_asset_download(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    desired = AssetDownloadInput.model_validate(modified.get("intent"))
    if desired != AssetDownloadPatch.model_validate(old.intent).asset_to_download.request:
        raise CommandRejected("INVALID_INPUT")
    async with get_db_context() as db:
        revised = await prepare_asset_download(db, old.actor_id, desired, command_id=old.command_id)
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
