"""Exact URL bytes and owned state are revalidated before original shared import writes."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_import_state import (
    SkillImportState,
    observe_skill_import_state,
)
from src.domains.agents.application.skill_package_import import (
    SkillPackageWrite,
    install_skill_package,
)
from src.domains.agents.application.skill_read import require_skill_access
from src.domains.agents.application.skill_url_import_schemas import (
    SkillUrlImportInput,
    SkillUrlImportPatch,
    SkillUrlImportSnapshot,
    canonical_skill_url_import,
)
from src.domains.agents.application.skill_url_import_spec import SKILL_URL_IMPORT_OPERATION
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import SkillProvenance
from src.domains.skills.url_import import fetch_skill_from_url
from src.domains.skills.url_rate_limit import rate_limit_url_import
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_skill_access(db, actor_id)
    if not settings.skills_url_import_enabled:
        raise CommandRejected("CAPABILITY_DISABLED")


async def _fetch(db: AsyncSession, actor_id: UUID, url: str) -> tuple[bytes, str]:
    await _access(db, actor_id)
    actor = await load_actor(db, actor_id)
    await db.commit()
    await rate_limit_url_import(actor)
    content, filename = await fetch_skill_from_url(url)
    await _access(db, actor_id)
    return content, filename


async def prepare_skill_url_import(
    db: AsyncSession,
    actor_id: UUID,
    request: SkillUrlImportInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = SkillUrlImportInput.model_validate(request.model_dump())
    content, filename = await _fetch(db, actor_id, desired.url)
    package = await SkillImportService(db).validate_upload(
        content, filename, owner_id=actor_id, provenance=SkillProvenance.URL
    )
    state = await observe_skill_import_state(db, actor_id, package.name, desired.replace_skill_id)
    snapshot = SkillUrlImportSnapshot(
        request=desired,
        filename=filename,
        size_bytes=len(content),
        package=package,
        previous=state.previous,
        package_digest=hashlib.sha256(content).hexdigest(),
        state_digest=state.digest,
    )
    if len(snapshot.model_dump_json().encode("utf-8")) > 64_000:
        raise CommandRejected("INVALID_INPUT")
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SKILL_URL_IMPORT_OPERATION,
        SkillUrlImportPatch(skill_url_import=snapshot),
        {"skill_url_import": state.previous.model_dump(mode="json") if state.previous else None},
        {"skill_url_import": snapshot.public_scope()},
        command_id=command_id,
    )


async def execute_skill_url_import(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SKILL_URL_IMPORT_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_skill_url_import(draft):
        raise CommandRejected("INVALID_INPUT")
    snapshot = SkillUrlImportPatch.model_validate(draft.intent).skill_url_import
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    content, filename = await _fetch(db, actor_id, snapshot.request.url)
    if (
        filename != snapshot.filename
        or len(content) != snapshot.size_bytes
        or hashlib.sha256(content).hexdigest() != snapshot.package_digest
    ):
        raise CommandRejected("STALE_STATE")
    await _install(db, actor_id, draft, snapshot, content, receipt)


async def _install(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    snapshot: SkillUrlImportSnapshot,
    content: bytes,
    receipt: PreferenceWriteReceipt,
) -> None:
    async def check(session: AsyncSession) -> None:
        await _access(session, actor_id)

    write = SkillPackageWrite(
        content=content,
        filename=snapshot.filename,
        name=snapshot.package.name,
        expected=SkillImportState(snapshot.previous, snapshot.state_digest),
        replace_skill_id=snapshot.request.replace_skill_id,
        provenance=SkillProvenance.URL,
        value_field="skill_url_import",
    )
    await install_skill_package(db, actor_id, draft, write, receipt, check)
