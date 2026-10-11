"""Native library writes reuse original import checks, quotas and commit acknowledgement."""

import asyncio
from collections.abc import Awaitable
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_import_state import require_absent_skill
from src.domains.agents.application.skill_library_import_schemas import (
    LibraryImportPatch,
    LibraryImportSnapshot,
    LibraryInstallInput,
    LibraryUpdateInput,
    canonical_library_import,
)
from src.domains.agents.application.skill_library_import_spec import (
    LIBRARY_INSTALL_OPERATION,
    LIBRARY_UPDATE_OPERATION,
)
from src.domains.agents.application.skill_read import require_skill_access
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skill_library import service
from src.domains.skill_library.errors import LibraryRefusal
from src.domains.skill_library.rate_limits import rate_limit_library
from src.domains.skill_library.repository import SkillLibraryRepository
from src.domains.skill_library.schemas import LibraryChanges, LibraryUpdatePreviewResponse
from src.domains.skills.import_commit import SkillImportCompletionUnknown
from src.domains.skills.import_service import validate_skill_name
from src.domains.skills.models import Skill
from src.domains.skills.removal import observe_removal
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


async def _library_result[Result](call: Awaitable[Result]) -> Result:
    try:
        return await call
    except LibraryRefusal as error:
        raise CommandRejected(error.code) from error


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_skill_access(db, actor_id)
    await require_capability_fresh(db, PlatformCapability.SKILL_LIBRARY)


async def _network_start(db: AsyncSession, actor_id: UUID) -> None:
    await _access(db, actor_id)
    actor = await load_actor(db, actor_id)
    await db.commit()
    await rate_limit_library(actor)


async def _state(
    db: AsyncSession,
    actor_id: UUID,
    request: LibraryInstallInput | LibraryUpdateInput,
    name: str,
    *,
    lock: bool = False,
) -> tuple[dict[str, JsonValue] | None, str]:
    validate_skill_name(name)
    if isinstance(request, LibraryInstallInput):
        await require_absent_skill(db, actor_id, name)
        return None, payload_digest({"absent": name})
    source = await SkillLibraryRepository(db).installed_skill(actor_id, request.skill_id)
    if source is None or source.name != name:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    removed = await observe_removal(db, actor_id, request.skill_id, lock=lock)
    public: dict[str, JsonValue] = {
        "source": {k: str(v) if isinstance(v, UUID) else v for k, v in asdict(source).items()},
        "skill": SkillReadItem.model_validate(removed.metadata).model_dump(mode="json"),
    }
    return public, payload_digest(
        {
            "source": public,
            "directory": str(removed.directory),
            "identity": list(removed.directory_identity) if removed.directory_identity else None,
            "archive": removed.archive_digest,
        }
    )


async def prepare_library_install(
    db: AsyncSession,
    actor_id: UUID,
    request: LibraryInstallInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = LibraryInstallInput.model_validate(request.model_dump())
    await _network_start(db, actor_id)
    preview = await _library_result(service.preview_install(actor_id, selected))
    if preview.blocked_by or preview.conflict != "none":
        raise CommandRejected("SOURCE_UNAVAILABLE")
    previous, witness = await _state(db, actor_id, selected, preview.name)
    await _access(db, actor_id)
    snapshot = LibraryImportSnapshot(
        kind="install",
        request=selected,
        preview=LibraryUpdatePreviewResponse(
            preview=preview, changes=LibraryChanges(added=[f.path for f in preview.files])
        ),
        previous=previous,
        state_digest=witness,
    )
    return _draft(actor_id, snapshot, command_id)


async def prepare_library_update(
    db: AsyncSession,
    actor_id: UUID,
    request: LibraryUpdateInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = LibraryUpdateInput.model_validate(request.model_dump())
    await _access(db, actor_id)
    source = await SkillLibraryRepository(db).installed_skill(actor_id, selected.skill_id)
    if source is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    previous, witness = await _state(db, actor_id, selected, source.name)
    await _network_start(db, actor_id)
    preview = await _library_result(
        service.update_preview(actor_id, selected.skill_id, commit_sha=selected.commit_sha)
    )
    if preview.preview.blocked_by:
        raise CommandRejected("SOURCE_UNAVAILABLE")
    if await _state(db, actor_id, selected, preview.preview.name) != (previous, witness):
        raise CommandRejected("STALE_STATE")
    await _access(db, actor_id)
    return _draft(
        actor_id,
        LibraryImportSnapshot(
            kind="update",
            request=selected,
            preview=preview,
            previous=previous,
            state_digest=witness,
        ),
        command_id,
    )


def _draft(
    actor_id: UUID, snapshot: LibraryImportSnapshot, command_id: UUID | None
) -> ApplicationActionDraftContent:
    if len(snapshot.model_dump_json().encode("utf-8")) > 64_000:
        raise CommandRejected("INVALID_INPUT")
    spec = LIBRARY_INSTALL_OPERATION if snapshot.kind == "install" else LIBRARY_UPDATE_OPERATION
    return build_action_content(
        actor_id,
        spec,
        LibraryImportPatch(skill_library_import=snapshot),
        {"skill_library_import": snapshot.previous},
        {"skill_library_import": snapshot.public_scope()},
        command_id=command_id,
    )


async def execute_library_import(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id not in {
        LIBRARY_INSTALL_OPERATION.operation_id,
        LIBRARY_UPDATE_OPERATION.operation_id,
    }:
        raise CommandRejected("FORBIDDEN")
    if not canonical_library_import(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = LibraryImportPatch.model_validate(draft.intent).skill_library_import
    expected_operation = (
        LIBRARY_INSTALL_OPERATION if selected.kind == "install" else LIBRARY_UPDATE_OPERATION
    )
    if draft.operation_id != expected_operation.operation_id:
        raise CommandRejected("INVALID_INPUT")
    await _perform_import(db, actor_id, draft, selected, receipt)


async def _perform_import(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    selected: LibraryImportSnapshot,
    receipt: PreferenceWriteReceipt,
) -> None:

    async def final_check(session: AsyncSession) -> None:
        await _access(session, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    async def before_swap(session: AsyncSession) -> None:
        await final_check(session)
        previous, witness = await _state(
            session, actor_id, selected.request, selected.preview.preview.name, lock=True
        )
        if previous != selected.previous or witness != selected.state_digest:
            raise CommandRejected("STALE_STATE")

    def committed(skill: Skill) -> None:
        receipt.committed = True
        receipt.values = {
            "skill_library_import": {
                "skill_id": str(skill.id),
                "name": skill.name,
                "commit_sha": selected.preview.preview.commit_sha,
            },
            "cache_refresh_pending": True,
        }

    await final_check(db)
    await _network_start(db, actor_id)
    try:
        if isinstance(selected.request, LibraryInstallInput):
            await service.install(
                actor_id,
                selected.request,
                before_swap=before_swap,
                before_commit=final_check,
                after_commit=committed,
                expected_preview=selected.preview.preview,
            )
        else:
            await service.update(
                actor_id,
                selected.request.skill_id,
                selected.request.commit_sha,
                before_swap=before_swap,
                before_commit=final_check,
                after_commit=committed,
                expected_preview=selected.preview.preview,
            )
    except SkillImportCompletionUnknown as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    except LibraryRefusal as error:
        raise CommandRejected(error.code) from error
    except (Exception, asyncio.CancelledError) as error:
        if not receipt.committed:
            raise
        logger.warning("native_skill_import_refresh_pending", error_type=type(error).__name__)
        return
    if receipt.values is not None:
        receipt.values["cache_refresh_pending"] = False
