"""One original-browser transfer freezes approved bytes and retains no saving claim."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadPatch,
    canonical_asset_download,
)
from src.domains.agents.application.asset_download_snapshot import open_asset_snapshot
from src.domains.agents.application.asset_download_spec import ASSET_DOWNLOAD_OPERATION
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.stored_download_service import (
    Check,
    StoredDownload,
    serve_stored_download_command,
)


async def serve_asset_download_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> StoredFileResponse:
    async def prepare(draft: ApplicationActionDraftContent, check: Check) -> StoredDownload:
        if not canonical_asset_download(draft):
            raise CommandRejected("INVALID_INPUT")
        expected = AssetDownloadPatch.model_validate(draft.intent).asset_to_download
        selected, reader = await open_asset_snapshot(db, actor_id, expected.request, lock=True)
        try:
            if selected != expected:
                raise CommandRejected("STALE_STATE")
            await check()
            await reader.freeze(max_bytes=selected.item.file_size)
            return StoredDownload(
                reader,
                selected.item.original_filename,
                selected.item.mime_type,
                {"asset_id": str(selected.request.asset_id)},
            )
        except BaseException:
            await reader.close()
            raise

    return await serve_stored_download_command(
        db,
        actor_id,
        command_id,
        origin,
        operation=ASSET_DOWNLOAD_OPERATION,
        prepare=prepare,
    )
