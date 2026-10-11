"""Receive bounded browser-selected bytes only after the durable original approval claim."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload_execution import FormParser, _selected_file
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_file_upload import read_skill_file_selection
from src.domains.agents.application.skill_file_upload_schemas import (
    SkillFileUploadPatch,
    canonical_skill_file_upload,
)
from src.domains.agents.application.skill_import_state import (
    SkillImportState,
    observe_skill_import_state,
)
from src.domains.agents.application.skill_package_import import (
    SkillPackageWrite,
    install_skill_package,
)
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import SkillProvenance
from src.domains.users.preference_cas import PreferenceWriteReceipt

FileCheck = Callable[[AsyncSession], Awaitable[None]]


def _accepted_values(receipt: PreferenceWriteReceipt) -> dict[str, JsonValue]:
    if not receipt.committed or receipt.values is None:
        raise CommandRejected("COMPLETION_UNKNOWN")
    receipt.values["upload_accepted"] = True
    return receipt.values


async def accept_skill_file_upload(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    check: FileCheck,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> dict[str, JsonValue]:
    if (
        file_confirmed is not True
        or draft.actor_id != actor_id
        or not canonical_skill_file_upload(draft)
    ):
        raise CommandRejected("INVALID_INPUT")
    selected = SkillFileUploadPatch.model_validate(draft.intent).skill_file_upload
    await check(db)
    if await read_skill_file_selection(db, actor_id, selected.request) != selected:
        raise CommandRejected("STALE_STATE")
    await db.commit()
    async with parse_form() as form:
        file = _selected_file(form)
        content = await file.read(selected.max_file_size_bytes + 1)
        if len(content) > selected.max_file_size_bytes:
            raise CommandRejected("CONSTRAINT_VIOLATION")
        await check(db)
        package = await SkillImportService(db).validate_upload(
            content, file.filename or "SKILL.md", owner_id=actor_id
        )
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        state = await observe_skill_import_state(
            db, actor_id, package.name, selected.request.replace_skill_id
        )
        if selected.previous is not None:
            state = SkillImportState(selected.previous, selected.state_digest or "")
        write = SkillPackageWrite(
            content=content,
            filename=file.filename or "SKILL.md",
            name=package.name,
            expected=state,
            replace_skill_id=selected.request.replace_skill_id,
            provenance=SkillProvenance.AUTHORED,
            value_field="skill_file_upload",
        )
        await install_skill_package(db, actor_id, draft, write, receipt, check)
        values = _accepted_values(receipt)
    return values
