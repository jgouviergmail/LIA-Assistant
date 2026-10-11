"""Only the approved original browser may claim and transfer one exact saved-copy export."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.core.stored_file_response import StoredFileResponse
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_download import open_skill_download
from src.domains.agents.application.skill_download_spec import SKILL_DOWNLOAD_OPERATION
from src.domains.agents.application.stored_download_service import (
    Check,
    StoredDownload,
    serve_stored_download_command,
)


async def serve_skill_download_command(
    db: AsyncSession, actor_id: UUID, command_id: UUID, origin: ApplicationOrigin | None
) -> StoredFileResponse:
    async def prepare(draft: ApplicationActionDraftContent, check: Check) -> StoredDownload:
        await check()
        return await open_skill_download(db, actor_id, draft)

    return await serve_stored_download_command(
        db, actor_id, command_id, origin, operation=SKILL_DOWNLOAD_OPERATION, prepare=prepare
    )
