"""One original package write boundary for URL bytes and human-selected browser files."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_import_state import (
    SkillImportState,
    observe_skill_import_state,
)
from src.domains.skills.import_commit import SkillImportCompletionUnknown
from src.domains.skills.import_service import SkillImportService
from src.domains.skills.models import Skill, SkillProvenance
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)
ImportCheck = Callable[[AsyncSession], Awaitable[None]]


@dataclass(frozen=True)
class SkillPackageWrite:
    content: bytes = field(repr=False)
    filename: str
    name: str
    expected: SkillImportState
    replace_skill_id: UUID | None
    provenance: SkillProvenance
    value_field: Literal["skill_url_import", "skill_file_upload"]


async def install_skill_package(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    write: SkillPackageWrite,
    receipt: PreferenceWriteReceipt,
    check: ImportCheck,
) -> None:
    async def final_check(session: AsyncSession) -> None:
        await check(session)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def before_swap(session: AsyncSession) -> None:
        await final_check(session)
        actual = await observe_skill_import_state(
            session, actor_id, write.name, write.replace_skill_id, lock=True
        )
        if actual != write.expected:
            raise CommandRejected("STALE_STATE")

    def committed(skill: Skill) -> None:
        receipt.committed = True
        receipt.values = {
            write.value_field: {
                "skill_id": str(skill.id),
                "name": skill.name,
                "provenance": write.provenance.value,
            },
            "cache_refresh_pending": True,
        }

    try:
        await SkillImportService(db).import_upload(
            write.content,
            write.filename,
            owner_id=actor_id,
            is_system=False,
            provenance=write.provenance,
            before_swap=before_swap,
            before_commit=final_check,
            after_commit=committed,
        )
    except SkillImportCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    except (Exception, asyncio.CancelledError) as error:
        if not receipt.committed:
            raise
        logger.warning("native_skill_package_refresh_pending", error_type=type(error).__name__)
        return
    if receipt.values is not None:
        receipt.values["cache_refresh_pending"] = False
