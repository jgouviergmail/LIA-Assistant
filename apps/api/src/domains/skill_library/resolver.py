"""Reading one skill of a repository, at one commit, before anything is written (ADR-327).

Everything an install needs is read here, and nothing here touches the
database: the folder is located, its size checked against the instance's
package bounds BEFORE a byte is downloaded, its manifest parsed by the same
loader that will load it, the portal's audits read, and every file downloaded
and verified against its blob SHA. The caller decides what to write.
"""

from __future__ import annotations

import asyncio
import posixpath
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import httpx

from src.core.config import settings
from src.core.constants import SKILL_LIBRARY_CHECK_CONCURRENCY, SKILL_LIBRARY_MAX_CANDIDATES
from src.domains.skill_library.errors import (
    AMBIGUOUS,
    INVALID_SKILL,
    NOT_FOUND,
    TOO_LARGE,
    LibraryRefusal,
)
from src.domains.skill_library.github import (
    SkillFolder,
    folder_of,
    read_file,
    read_tree,
    skill_folders,
)
from src.domains.skill_library.portals import (
    DEFAULT_PORTAL,
    PORTALS,
    AuditVerdict,
    blocking_risk,
)

_MANIFEST: Final = "SKILL.md"
_UTF8_BOM: Final = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class ReadSkill:
    """One skill folder read at a commit, with what the portal says of it."""

    folder: SkillFolder
    name: str
    description: str
    audits: list[AuditVerdict] | None
    blocked_by: str | None

    @property
    def has_scripts(self) -> bool:
        """Whether the folder ships scripts (they run in the sandbox)."""
        return any(f.path.startswith("scripts/") for f in self.folder.files)


def _full_path(folder: SkillFolder, relative: str) -> str:
    return f"{folder.path}/{relative}" if folder.path else relative


def check_budget(folder: SkillFolder) -> None:
    """Refuse a folder larger than any package the instance accepts.

    Raises:
        LibraryRefusal: ``skill_library_too_large`` with the bound it passed.
    """
    max_files = settings.skills_zip_max_files
    max_kb = settings.skills_zip_max_decompressed_kb
    if len(folder.files) > max_files:
        raise LibraryRefusal(TOO_LARGE, max_files=max_files)
    if sum(f.size for f in folder.files) > max_kb * 1024:
        raise LibraryRefusal(TOO_LARGE, max_kb=max_kb)


def _parse_manifest(content: bytes) -> dict[str, Any] | None:
    """The manifest as the skill loader reads it (runs in a worker thread)."""
    from src.domains.skills.loader import parse_skill_file

    with tempfile.TemporaryDirectory(prefix="skill_library_") as root:
        manifest = Path(root) / _MANIFEST
        manifest.write_bytes(content.removeprefix(_UTF8_BOM))
        # A temporary folder has a random name: the installed-folder
        # convention (name == folder) cannot apply to it.
        return parse_skill_file(manifest, check_dir_name=False)


async def read_manifest(client: httpx.AsyncClient, folder: SkillFolder) -> dict[str, Any]:
    """The folder's SKILL.md, verified and parsed.

    Raises:
        LibraryRefusal: ``skill_library_invalid_skill`` when the loader refuses it.
    """
    entry = next(f for f in folder.files if f.path == _MANIFEST)
    content = await read_file(
        client, folder.repository, folder.commit_sha, _full_path(folder, _MANIFEST), entry.sha
    )
    parsed = await asyncio.to_thread(_parse_manifest, content)
    if not parsed or not parsed.get("name") or not parsed.get("description"):
        raise LibraryRefusal(INVALID_SKILL)
    return parsed


async def _manifest_name(client: httpx.AsyncClient, folder: SkillFolder) -> str:
    """A candidate's name; a manifest the loader refuses names nothing.

    Any other refusal (GitHub unreachable, its allowance spent) is the answer
    itself, never a « not found ».
    """
    try:
        return str((await read_manifest(client, folder)).get("name", ""))
    except LibraryRefusal as refusal:
        if refusal.code != INVALID_SKILL:
            raise
        return ""


async def locate(
    client: httpx.AsyncClient,
    listing: dict[str, Any],
    *,
    repository: str,
    ref: str,
    commit_sha: str,
    skill_id: str,
) -> str:
    """The folder a portal's ``skill_id`` names in a repository.

    A folder named like the skill wins; otherwise the manifests of the
    candidates (at most ``SKILL_LIBRARY_MAX_CANDIDATES``) are read and the one
    whose name is ``skill_id`` is taken.

    Raises:
        LibraryRefusal: ``not_found`` when none is, ``ambiguous`` when several are.
    """
    folders = skill_folders(listing)
    repo_name = repository.partition("/")[2]
    named = [
        f
        for f in folders
        if posixpath.basename(f) == skill_id or (f == "" and repo_name == skill_id)
    ]
    if len(named) == 1:
        return named[0]
    candidates = (named or folders)[:SKILL_LIBRARY_MAX_CANDIDATES]
    gate = asyncio.Semaphore(SKILL_LIBRARY_CHECK_CONCURRENCY)

    async def name_of(path: str) -> str:
        async with gate:
            folder = folder_of(listing, repository, ref, commit_sha, path)
            return await _manifest_name(client, folder)

    names = await asyncio.gather(*(name_of(f) for f in candidates))
    matches = [f for f, name in zip(candidates, names, strict=True) if name == skill_id]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise LibraryRefusal(AMBIGUOUS, folders=matches)
    raise LibraryRefusal(NOT_FOUND)


async def audit(
    client: httpx.AsyncClient, portal: str | None, repository: str, audit_ids: list[str]
) -> tuple[list[AuditVerdict] | None, str | None]:
    """The portal's audits of one skill, and the risk that refuses it here, if any.

    The skill is looked up under EVERY name it may be audited under — the
    portal's identifier, its manifest name, its folder — and the verdicts are
    pooled: a folder named differently must not be a way around a refusal.
    """
    verdicts = await PORTALS[portal or DEFAULT_PORTAL].audit(client, repository, audit_ids)
    if verdicts is None:
        return None, None
    found = [verdict for audit_id in audit_ids for verdict in verdicts.get(audit_id, [])]
    return found, blocking_risk(found, settings.skill_library_audit_block_level)


async def read_skill(
    client: httpx.AsyncClient,
    listing: dict[str, Any],
    *,
    repository: str,
    ref: str,
    commit_sha: str,
    path: str,
    portal: str | None,
    audit_id: str | None,
) -> ReadSkill:
    """Read the folder ``path`` of a listing: bounds, manifest, audits.

    Raises:
        LibraryRefusal: When the folder is missing, too large, or its manifest refused.
    """
    folder = folder_of(listing, repository, ref, commit_sha, path)
    check_budget(folder)
    manifest = await read_manifest(client, folder)
    name = str(manifest["name"])
    audit_ids = sorted({i for i in (audit_id, name, posixpath.basename(path)) if i})
    audits, blocked_by = await audit(client, portal, repository, audit_ids)
    return ReadSkill(folder, name, str(manifest["description"]), audits, blocked_by)


async def read_at_commit(
    client: httpx.AsyncClient,
    *,
    repository: str,
    ref: str,
    commit_sha: str,
    path: str,
    portal: str | None,
    audit_id: str | None,
) -> ReadSkill:
    """:func:`read_skill` on the listing of ``commit_sha``."""
    listing = await read_tree(client, repository, commit_sha)
    return await read_skill(
        client,
        listing,
        repository=repository,
        ref=ref,
        commit_sha=commit_sha,
        path=path,
        portal=portal,
        audit_id=audit_id,
    )


async def download(client: httpx.AsyncClient, folder: SkillFolder) -> dict[str, bytes]:
    """Every file of the folder, each verified against its blob SHA."""
    gate = asyncio.Semaphore(SKILL_LIBRARY_CHECK_CONCURRENCY)

    async def one(relative: str, sha: str) -> bytes:
        async with gate:
            return await read_file(
                client, folder.repository, folder.commit_sha, _full_path(folder, relative), sha
            )

    contents = await asyncio.gather(*(one(f.path, f.sha) for f in folder.files))
    return {f.path: data for f, data in zip(folder.files, contents, strict=True)}
