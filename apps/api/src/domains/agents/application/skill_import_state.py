"""Shared exact owned-file witnesses and absent personal import destinations."""

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.effects.digest import payload_digest
from src.domains.skills.import_service import validate_skill_name
from src.domains.skills.removal import observe_removal
from src.domains.skills.repository import SkillRepository


@dataclass(frozen=True)
class SkillImportState:
    previous: SkillReadItem | None
    digest: str


async def require_absent_skill(db: AsyncSession, actor_id: UUID, name: str) -> None:
    validate_skill_name(name)
    account = Path(settings.skills_users_path) / str(actor_id)
    directory = account / name
    if (
        account.is_symlink()
        or account.is_junction()
        or directory.exists()
        or directory.is_symlink()
        or directory.is_junction()
    ):
        raise CommandRejected("STALE_STATE")
    if await SkillRepository(db).get_owned(actor_id, name) is not None:
        raise CommandRejected("STALE_STATE")


async def observe_skill_import_state(
    db: AsyncSession,
    actor_id: UUID,
    name: str,
    replace_skill_id: UUID | None,
    *,
    lock: bool = False,
) -> SkillImportState:
    if replace_skill_id is None:
        await require_absent_skill(db, actor_id, name)
        return SkillImportState(None, payload_digest({"absent": name}))
    observed = await observe_removal(db, actor_id, replace_skill_id, lock=lock)
    if observed.name != name:
        raise CommandRejected("INVALID_INPUT")
    previous = SkillReadItem.model_validate(observed.metadata)
    return SkillImportState(
        previous,
        payload_digest(
            {
                "skill": previous.model_dump(mode="json"),
                "directory": str(observed.directory),
                "identity": (
                    list(observed.directory_identity) if observed.directory_identity else None
                ),
                "archive": observed.archive_digest,
            }
        ),
    )
