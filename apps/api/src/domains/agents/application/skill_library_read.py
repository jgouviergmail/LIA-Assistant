"""Original library ports own network/cache/audit policy; native reads retain fresh authority."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.skill_library_read_schemas import (
    LibraryInstalledInput,
    LibraryListPath,
    LibraryListWindow,
    LibraryPreviewInput,
    LibraryReadData,
    LibrarySearchInput,
    SkillLibraryReadInput,
    SkillLibraryReadProjection,
)
from src.domains.agents.application.skill_read import require_skill_access
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skill_library import service
from src.domains.skill_library.rate_limits import rate_limit_library

LIST_PATHS: tuple[LibraryListPath, ...] = (
    "items",
    "preview.files",
    "preview.skipped",
    "preview.audits",
    "choice.folders",
    "changes.added",
    "changes.removed",
    "changes.modified",
)


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_skill_access(db, actor_id)
    await require_capability_fresh(db, PlatformCapability.SKILL_LIBRARY)


async def _lookup(actor_id: UUID, query: SkillLibraryReadInput) -> LibraryReadData:
    request = query.request
    if isinstance(request, LibrarySearchInput):
        return await service.search(actor_id, request.q, request.portal)
    if isinstance(request, LibraryInstalledInput):
        return await service.installed(actor_id)
    if isinstance(request, LibraryPreviewInput):
        return await service.preview(
            actor_id,
            repository=request.repository,
            address=request.address,
            skill_id=request.skill_id,
            path=request.path.strip("/") if request.path is not None else None,
            ref=request.ref,
            portal=request.portal,
            registry_id=request.registry_id,
        )
    return await service.update_preview(actor_id, request.skill_id)


def _page(
    data: LibraryReadData, query: SkillLibraryReadInput
) -> tuple[LibraryReadData, dict[LibraryListPath, LibraryListWindow]]:
    values = data.model_dump(mode="json")
    windows: dict[LibraryListPath, LibraryListWindow] = {}
    for path in LIST_PATHS:
        container = values
        parts = path.split(".")
        for part in parts[:-1]:
            nested = container.get(part)
            if not isinstance(nested, dict):
                container = {}
                break
            container = nested
        if not isinstance(container, dict):
            continue
        items = container.get(parts[-1])
        if not isinstance(items, list):
            continue
        container[parts[-1]] = items[query.offset : query.offset + query.limit]
        end = query.offset + len(container[parts[-1]])
        windows[path] = LibraryListWindow(
            total=len(items), next_offset=end if end < len(items) else None
        )
    return type(data).model_validate(values), windows


async def read_skill_library(
    db: AsyncSession, actor_id: UUID, query: SkillLibraryReadInput
) -> SkillLibraryReadProjection:
    selected = SkillLibraryReadInput.model_validate(query.model_dump())
    await _access(db, actor_id)
    user = await load_actor(db, actor_id)
    await db.commit()
    await rate_limit_library(user)
    data = await _lookup(actor_id, selected)
    await _access(db, actor_id)
    paged, windows = _page(data, selected)
    result = SkillLibraryReadProjection(observed_at=datetime.now(UTC), data=paged, windows=windows)
    if len(result.model_dump_json().encode("utf-8")) > 64_000:
        raise ValueError("Library projection too large; request a smaller page")
    return result
