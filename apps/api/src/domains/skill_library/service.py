"""Searching, installing and updating skills from a library (ADR-327).

The library is a door into the ONE import pipeline: an install reads a
repository folder at the commit its preview showed (``resolver.py``), then
hands the files to ``SkillImportService.import_directory`` with the
``library`` provenance — the same S1-S5 checks, conflicts and quota as every
other import — and records where they came from in the registration's own
transaction. Removing an installed skill is the skills section's ordinary
delete: the provenance row cascades.

No database session is ever held across a network call (ADR-304): every read
of the account's state opens a short session of its own, BEFORE or AFTER the
network, and the import's session opens once every file is already local.
"""

from __future__ import annotations

import asyncio
import posixpath
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    SKILL_LIBRARY_CHECK_CONCURRENCY,
    SKILL_LIBRARY_QUERY_MAX_CHARS,
    SKILL_LIBRARY_QUERY_MIN_CHARS,
)
from src.core.exceptions import BaseAPIException
from src.domains.skill_library.errors import (
    ALREADY_INSTALLED,
    AUDIT_BLOCKED,
    INVALID_SKILL,
    NAME_TAKEN,
    NOT_FOUND,
    NOT_INSTALLED,
    QUERY_INVALID,
    QUOTA_REACHED,
    RENAMED,
    SOURCE_INVALID,
    LibraryRefusal,
)
from src.domains.skill_library.github import (
    DEFAULT_REF,
    ORIGIN_GITHUB,
    folder_tree_sha,
    parse_address,
    read_tree,
    resolve_commit,
    safe_relative,
    skill_folders,
    valid_ref,
    valid_repository,
)
from src.domains.skill_library.portals import DEFAULT_PORTAL, PORTALS
from src.domains.skill_library.repository import (
    InstalledSkill,
    SkillLibraryRepository,
    SourceRecord,
)
from src.domains.skill_library.resolver import (
    ReadSkill,
    download,
    locate,
    read_at_commit,
    read_skill,
)
from src.domains.skill_library.schemas import (
    Conflict,
    LibraryAudit,
    LibraryChanges,
    LibraryFile,
    LibraryFolderChoice,
    LibraryInstalledItem,
    LibraryInstalledResponse,
    LibraryInstallRequest,
    LibraryInstallResponse,
    LibraryPreviewAnswer,
    LibraryPreviewResponse,
    LibrarySearchItem,
    LibrarySearchResponse,
    LibraryUpdatePreviewResponse,
    UpdateState,
)
from src.domains.skills.exceptions import ImportRefusalKind, import_refusal_kind
from src.infrastructure.database.session import get_db_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.skills.models import Skill

logger = structlog.get_logger(__name__)

#: What the import pipeline's refusals mean to a library install.
_IMPORT_REFUSALS: Final[dict[ImportRefusalKind, str]] = {
    "name_taken": NAME_TAKEN,
    "quota_reached": QUOTA_REACHED,
    "invalid": INVALID_SKILL,
}


def _client() -> httpx.AsyncClient:
    """One client per operation: owned by it, closed with it."""
    return httpx.AsyncClient()


def _preview_of(
    read: ReadSkill,
    *,
    portal: str | None,
    registry_id: str | None,
    conflict: Conflict,
) -> LibraryPreviewResponse:
    folder = read.folder
    return LibraryPreviewResponse(
        portal=portal,
        registry_id=registry_id,
        repository=folder.repository,
        ref=folder.ref,
        path=folder.path,
        commit_sha=folder.commit_sha,
        tree_sha=folder.tree_sha,
        name=read.name,
        description=read.description,
        files=[LibraryFile(path=f.path, size=f.size) for f in folder.files],
        skipped=list(folder.skipped),
        has_scripts=read.has_scripts,
        audits=(
            None
            if read.audits is None
            else [
                LibraryAudit(provider=a.provider, risk=a.risk, alerts=a.alerts) for a in read.audits
            ]
        ),
        blocked_by=read.blocked_by,
        conflict=conflict,
    )


def _check_repository(repository: str, path: str, ref: str = DEFAULT_REF) -> None:
    """Refuse a repository, a folder or a ref that does not read as one."""
    if not valid_repository(repository) or not valid_ref(ref):
        raise LibraryRefusal(SOURCE_INVALID)
    if path and not safe_relative(path):
        raise LibraryRefusal(SOURCE_INVALID)


def _portal_of(portal: str | None) -> str | None:
    """A portal key the library knows, or None (a pasted address).

    Raises:
        LibraryRefusal: ``skill_library_source_invalid`` for a portal it does not know.
    """
    if portal is not None and portal not in PORTALS:
        raise LibraryRefusal(SOURCE_INVALID)
    return portal


async def _installed_rows(user_id: UUID) -> list[InstalledSkill]:
    async with get_db_context() as db:
        return await SkillLibraryRepository(db).installed(user_id)


async def _conflict(user_id: UUID, name: str, repository: str, path: str) -> Conflict:
    """Whether ``name`` is free for this folder in the caller's library.

    A system skill's name is never taken by a library skill: shadowing a skill
    the person relies on with one written elsewhere is how a stranger's text
    would answer a request meant for LIA's own.
    """
    from src.domains.skills.cache import SkillsCache
    from src.domains.skills.repository import SkillRepository

    if SkillsCache.get_system_by_name(name) is not None:
        return "name_taken"
    async with get_db_context() as db:
        skills = SkillRepository(db)
        if await skills.get_system(name) is not None:
            return "name_taken"
        owned = await skills.get_owned(user_id, name)
        source = (
            await SkillLibraryRepository(db).installed_skill(user_id, owned.id) if owned else None
        )
    if owned is None:
        return "none"
    if source and source.repository == repository and source.path == path:
        return "installed"
    return "name_taken"


def _write_folder(root: Path, files: dict[str, bytes]) -> None:
    """Lay the downloaded files out (worker thread); paths were checked when listed."""
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


async def _register(
    user_id: UUID, read: ReadSkill, files: dict[str, bytes], record: SourceRecord
) -> LibraryInstallResponse:
    """Hand the files to the import pipeline and record their provenance with them."""
    from src.domains.skills.import_service import SkillImportService
    from src.domains.skills.models import SkillProvenance

    registered_ids: list[UUID] = []

    async def keep_source(db: AsyncSession, skill: Skill) -> None:
        await SkillLibraryRepository(db).record(skill.id, record)
        registered_ids.append(skill.id)

    with tempfile.TemporaryDirectory(prefix="skill_library_") as root:
        folder = Path(root) / "skill"
        await asyncio.to_thread(_write_folder, folder, files)
        try:
            async with get_db_context() as db:
                registered = await SkillImportService(db).import_directory(
                    folder,
                    owner_id=user_id,
                    provenance=SkillProvenance.LIBRARY,
                    after_register=keep_source,
                )
        except BaseAPIException as exc:
            code = _IMPORT_REFUSALS[import_refusal_kind(exc)]
            reason = exc.detail if code == INVALID_SKILL and isinstance(exc.detail, str) else None
            raise LibraryRefusal(code, reason=reason) from exc
    if not registered_ids:
        raise LibraryRefusal(INVALID_SKILL)
    logger.info(
        "skill_library_installed",
        repository=record.repository,
        commit_sha=record.commit_sha,
        files=len(files),
    )
    return LibraryInstallResponse(
        skill_id=registered_ids[0],
        name=str(registered.get("name", read.name)),
        commit_sha=record.commit_sha,
    )


async def search(user_id: UUID, query: str, portal: str | None) -> LibrarySearchResponse:
    """A portal's answer to ``query``, with what the caller already installed.

    Raises:
        LibraryRefusal: On a text out of bounds, an unknown portal, or a portal
            that cannot be read.
    """
    text = " ".join(query.split())
    key = portal or DEFAULT_PORTAL
    if not SKILL_LIBRARY_QUERY_MIN_CHARS <= len(text) <= SKILL_LIBRARY_QUERY_MAX_CHARS:
        raise LibraryRefusal(
            QUERY_INVALID,
            min_chars=SKILL_LIBRARY_QUERY_MIN_CHARS,
            max_chars=SKILL_LIBRARY_QUERY_MAX_CHARS,
        )
    if key not in PORTALS:
        raise LibraryRefusal(SOURCE_INVALID)
    async with _client() as client:
        entries = await PORTALS[key].search(client, text, settings.skill_library_search_limit)
    installed = await _installed_rows(user_id)
    registry_ids = {row.registry_id for row in installed if row.registry_id}
    folders = {(row.repository, posixpath.basename(row.path)) for row in installed}
    return LibrarySearchResponse(
        portal=key,
        items=[
            LibrarySearchItem(
                registry_id=e.registry_id,
                name=e.name,
                source=e.source,
                skill_id=e.skill_id,
                installs=e.installs,
                repository=e.repository,
                supported=e.repository is not None,
                installed=e.registry_id in registry_ids or (e.source, e.skill_id) in folders,
            )
            for e in entries
        ],
    )


def _preview_target(
    repository: str | None, address: str | None, path: str | None, ref: str | None
) -> tuple[str, str | None, str]:
    """The repository, folder and ref a preview reads: from an address, or given.

    Raises:
        LibraryRefusal: ``skill_library_source_invalid`` when they do not read as one.
    """
    target = parse_address(address) if address else None
    repo = target.repository if target else (repository or "")
    folder_path = path if path is not None else (target.path if target else None)
    followed = ref or (target.ref if target else None) or DEFAULT_REF
    _check_repository(repo, folder_path or "", followed)
    return repo, folder_path, followed


def _only_folder(
    listing: dict[str, object], repository: str, ref: str, commit_sha: str
) -> str | LibraryFolderChoice:
    """The one skill folder of a repository, or the folders to choose from.

    Raises:
        LibraryRefusal: ``skill_library_not_found`` when it holds no skill.
    """
    folders = skill_folders(listing)
    if not folders:
        raise LibraryRefusal(NOT_FOUND)
    if len(folders) > 1:
        return LibraryFolderChoice(
            repository=repository, ref=ref, commit_sha=commit_sha, folders=folders
        )
    return folders[0]


async def preview(
    user_id: UUID,
    *,
    repository: str | None = None,
    address: str | None = None,
    skill_id: str | None = None,
    path: str | None = None,
    ref: str | None = None,
    portal: str | None = None,
    registry_id: str | None = None,
) -> LibraryPreviewAnswer:
    """Read a skill before installing it, or the folders to choose from first.

    Either a ``repository`` (with a portal's ``skill_id``) or a pasted
    ``address``; a ``path`` names the folder directly.

    Raises:
        LibraryRefusal: When the source is unreadable or names no skill.
    """
    repo, folder_path, followed = _preview_target(repository, address, path, ref)
    portal = _portal_of(portal)
    async with _client() as client:
        commit = await resolve_commit(client, repo, followed)
        listing = await read_tree(client, repo, commit)
        if folder_path is None and skill_id:
            folder_path = await locate(
                client, listing, repository=repo, ref=followed, commit_sha=commit, skill_id=skill_id
            )
        if folder_path is None:
            only = _only_folder(listing, repo, followed, commit)
            if isinstance(only, LibraryFolderChoice):
                return LibraryPreviewAnswer(choice=only)
            folder_path = only
        read = await read_skill(
            client,
            listing,
            repository=repo,
            ref=followed,
            commit_sha=commit,
            path=folder_path,
            portal=portal,
            audit_id=skill_id,
        )
    conflict = await _conflict(user_id, read.name, repo, folder_path)
    shown = _preview_of(read, portal=portal, registry_id=registry_id, conflict=conflict)
    return LibraryPreviewAnswer(preview=shown)


async def install(user_id: UUID, request: LibraryInstallRequest) -> LibraryInstallResponse:
    """Install the folder a preview showed, at the commit it showed.

    Raises:
        LibraryRefusal: On an audit that refuses it, a name already taken, a
            skill already installed from there, or anything the import refuses.
    """
    _check_repository(request.repository, request.path, request.ref)
    portal = _portal_of(request.portal)
    async with _client() as client:
        read = await read_at_commit(
            client,
            repository=request.repository,
            ref=request.ref,
            commit_sha=request.commit_sha,
            path=request.path,
            portal=portal,
            audit_id=request.skill_id,
        )
        if read.blocked_by:
            raise LibraryRefusal(AUDIT_BLOCKED, risk=read.blocked_by)
        conflict = await _conflict(user_id, read.name, request.repository, request.path)
        if conflict == "installed":
            raise LibraryRefusal(ALREADY_INSTALLED)
        if conflict == "name_taken":
            raise LibraryRefusal(NAME_TAKEN)
        files = await download(client, read.folder)
    record = SourceRecord(
        portal=request.portal,
        origin=ORIGIN_GITHUB,
        repository=request.repository,
        ref=request.ref,
        path=request.path,
        registry_id=request.registry_id,
        commit_sha=read.folder.commit_sha,
        tree_sha=read.folder.tree_sha,
    )
    return await _register(user_id, read, files, record)


async def _installed_skill(user_id: UUID, skill_id: UUID) -> InstalledSkill:
    async with get_db_context() as db:
        found = await SkillLibraryRepository(db).installed_skill(user_id, skill_id)
    if found is None:
        raise LibraryRefusal(NOT_INSTALLED)
    return found


async def _head_listing(
    client: httpx.AsyncClient, gate: asyncio.Semaphore, repository: str, ref: str
) -> dict[str, Any] | None:
    """The listing at the head of ``ref`` now, or None when it cannot be read."""
    async with gate:
        try:
            commit = await resolve_commit(client, repository, ref)
            return await read_tree(client, repository, commit)
        except LibraryRefusal:
            return None


def _state_of(row: InstalledSkill, listing: dict[str, Any] | None) -> UpdateState:
    """Whether the folder moved since it was installed: its tree SHA is the version."""
    current = folder_tree_sha(listing, row.path) if listing is not None else ""
    if not current:
        return "unknown"
    return "current" if current == row.tree_sha else "available"


async def installed(user_id: UUID) -> LibraryInstalledResponse:
    """Every skill the caller installed from a library, and whether it moved.

    Each repository and ref is read ONCE, however many of its skills are
    installed: GitHub's anonymous allowance is the instance's.
    """
    rows = await _installed_rows(user_id)
    sources = sorted({(row.repository, row.ref) for row in rows})
    gate = asyncio.Semaphore(SKILL_LIBRARY_CHECK_CONCURRENCY)
    async with _client() as client:
        listings = await asyncio.gather(*(_head_listing(client, gate, *s) for s in sources))
    by_source = dict(zip(sources, listings, strict=True))
    states = [_state_of(row, by_source[(row.repository, row.ref)]) for row in rows]
    return LibraryInstalledResponse(
        items=[
            LibraryInstalledItem(
                skill_id=row.skill_id,
                name=row.name,
                portal=row.portal,
                repository=row.repository,
                path=row.path,
                ref=row.ref,
                commit_sha=row.commit_sha,
                update=state,
            )
            for row, state in zip(rows, states, strict=True)
        ]
    )


def _blobs(listing: dict[str, object]) -> dict[str, str]:
    tree = listing.get("tree")
    return {
        str(e["path"]): str(e.get("sha", ""))
        for e in (tree if isinstance(tree, list) else [])
        if isinstance(e, dict) and e.get("type") == "blob" and "path" in e
    }


async def update_preview(user_id: UUID, skill_id: UUID) -> LibraryUpdatePreviewResponse:
    """The version an update would install, and the files it changes.

    Raises:
        LibraryRefusal: When the skill is not a library skill of the caller, or
            its folder can no longer be read.
    """
    row = await _installed_skill(user_id, skill_id)
    async with _client() as client:
        commit = await resolve_commit(client, row.repository, row.ref)
        read = await read_at_commit(
            client,
            repository=row.repository,
            ref=row.ref,
            commit_sha=commit,
            path=row.path,
            portal=row.portal,
            audit_id=posixpath.basename(row.path) or None,
        )
        before = _blobs(await read_tree(client, row.repository, row.tree_sha))
    after = {f.path: f.sha for f in read.folder.files}
    changes = LibraryChanges(
        added=sorted(set(after) - set(before)),
        removed=sorted(set(before) - set(after)),
        modified=sorted(p for p in set(after) & set(before) if after[p] != before[p]),
    )
    shown = _preview_of(read, portal=row.portal, registry_id=row.registry_id, conflict="installed")
    return LibraryUpdatePreviewResponse(preview=shown, changes=changes)


async def update(user_id: UUID, skill_id: UUID, commit_sha: str) -> LibraryInstallResponse:
    """Install the version an update preview showed, in place of the current one.

    Raises:
        LibraryRefusal: When the skill is not the caller's library skill, the
            new version is refused by an audit, carries another name, or is
            refused by the import.
    """
    row = await _installed_skill(user_id, skill_id)
    async with _client() as client:
        read = await read_at_commit(
            client,
            repository=row.repository,
            ref=row.ref,
            commit_sha=commit_sha,
            path=row.path,
            portal=row.portal,
            audit_id=posixpath.basename(row.path) or None,
        )
        if read.blocked_by:
            raise LibraryRefusal(AUDIT_BLOCKED, risk=read.blocked_by)
        if read.name != row.name:
            raise LibraryRefusal(RENAMED, name=read.name)
        files = await download(client, read.folder)
    record = SourceRecord(
        portal=row.portal,
        origin=ORIGIN_GITHUB,
        repository=row.repository,
        ref=row.ref,
        path=row.path,
        registry_id=row.registry_id,
        commit_sha=read.folder.commit_sha,
        tree_sha=read.folder.tree_sha,
    )
    return await _register(user_id, read, files, record)
