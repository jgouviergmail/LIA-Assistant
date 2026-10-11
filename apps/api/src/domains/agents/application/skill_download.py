"""Only a current visible skill reaches the approved browser as frozen complete archive bytes."""

import asyncio
import hashlib
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.skill_download_schemas import (
    SkillDownloadInput,
    SkillDownloadPatch,
    SkillDownloadSnapshot,
    canonical_skill_download,
)
from src.domains.agents.application.skill_download_spec import SKILL_DOWNLOAD_OPERATION
from src.domains.agents.application.skill_read import observe_visible_skill, require_skill_access
from src.domains.agents.application.stored_download_service import StoredDownload
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.skills.archive import create_skill_archive
from src.domains.skills.cache import SkillsCache
from src.domains.skills.personal_state import personal_state
from src.infrastructure.file_transfer import LocalFileRead


async def _snapshot(
    db: AsyncSession, actor_id: UUID, request: SkillDownloadInput, *, lock: bool = False
) -> tuple[SkillDownloadSnapshot, bytes]:
    await require_skill_access(db, actor_id)
    if lock:
        await personal_state(db, actor_id, request.skill_id)
    metadata = await observe_visible_skill(db, actor_id, request.skill_id)
    cached = SkillsCache.get_exact(
        metadata.name, str(actor_id) if metadata.scope == "user" else None
    )
    if cached is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    if cached.get("scope") != metadata.scope or cached.get("owner_id") != (
        str(actor_id) if metadata.scope == "user" else None
    ):
        raise CommandRejected("FORBIDDEN")
    archive = await asyncio.to_thread(create_skill_archive, cached)
    await require_skill_access(db, actor_id)
    if await observe_visible_skill(db, actor_id, request.skill_id) != metadata:
        raise CommandRejected("STALE_STATE")
    return (
        SkillDownloadSnapshot(
            request=request,
            skill=metadata,
            filename=f"{metadata.name}.zip",
            file_bytes=len(archive),
            state_digest=hashlib.sha256(archive).hexdigest(),
        ),
        archive,
    )


async def prepare_skill_download(
    db: AsyncSession, actor_id: UUID, request: SkillDownloadInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    scope, _ = await _snapshot(
        db, actor_id, SkillDownloadInput.model_validate(request.model_dump())
    )
    await authorize_management_export(db, actor_id, context.application_origin)
    return build_action_content(
        actor_id,
        SKILL_DOWNLOAD_OPERATION,
        SkillDownloadPatch(skill_to_download=scope),
        {"skill_to_download": None},
        {"skill_to_download": scope.public_scope()},
        command_id=command_id,
    )


async def open_skill_download(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> StoredDownload:
    if draft.actor_id != actor_id or draft.operation_id != SKILL_DOWNLOAD_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_skill_download(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = SkillDownloadPatch.model_validate(draft.intent).skill_to_download
    actual, archive = await _snapshot(db, actor_id, expected.request, lock=True)
    if actual != expected:
        raise CommandRejected("STALE_STATE")
    return StoredDownload(
        await LocalFileRead.async_from_bytes(archive),
        actual.filename,
        actual.content_type,
        {"skill_id": str(expected.request.skill_id)},
    )
