"""A skill's ORIGIN on GitHub: a folder of a public repository, read at a commit (ADR-327).

The portal only indexes; the files live in a repository. Everything here reads
GitHub's public REST API and raw host through :func:`http.fetch`, and nothing
is trusted that could have changed between two reads:

- a branch is resolved ONCE to a commit, and every later read names that
  commit — an install is the content its preview showed;
- a file is verified against the blob SHA the listing gave for it
  (``sha1("blob <size>\\0" + bytes)``, git's own identity);
- a folder's identity is its git TREE SHA: two commits that leave it untouched
  are the same skill, which is what an update check compares;
- a symbolic link or a submodule is never followed — it is reported, skipped.

Anonymous, GitHub allows the whole instance 60 API requests per hour, so a
branch head is cached briefly and a listing at a commit for the day
(``cache.py``); an optional token lifts the limit and reaches api.github.com
alone.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import quote, urlparse

import httpx

from src.core.config import settings
from src.core.constants import (
    SKILL_LIBRARY_GITHUB_API_URL,
    SKILL_LIBRARY_GITHUB_RAW_URL,
    SKILL_LIBRARY_TREE_CACHE_TTL_SECONDS,
)
from src.domains.skill_library import cache
from src.domains.skill_library.errors import (
    NOT_FOUND,
    RATE_LIMITED,
    SOURCE_INVALID,
    TOO_LARGE,
    UNREACHABLE,
    LibraryRefusal,
)
from src.domains.skill_library.http import Fetched, FetchOutcome, fetch

#: The origin key stored with an installed skill.
ORIGIN_GITHUB: Final = "github"
#: The ref an install follows when the person names none: the default branch.
DEFAULT_REF: Final = "HEAD"
_MANIFEST: Final = "SKILL.md"
_SYMLINK_MODE: Final = "120000"
_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_OWNER_RE: Final = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
#: A ref is a branch or tag name; bounded, and never able to leave its segment.
_REF_RE: Final = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


@dataclass(frozen=True)
class RepoFile:
    """One regular file of a skill folder, as the listing gave it."""

    path: str  # relative to the skill folder
    size: int
    sha: str  # git blob SHA


@dataclass(frozen=True)
class SkillFolder:
    """A skill folder of a repository, at one commit."""

    repository: str
    ref: str
    commit_sha: str
    path: str  # '' = the repository root
    tree_sha: str
    files: tuple[RepoFile, ...]
    skipped: tuple[str, ...] = field(default=())  # links and submodules, never read


@dataclass(frozen=True)
class GithubAddress:
    """What a pasted GitHub address names."""

    repository: str
    ref: str | None = None
    path: str | None = None


def _refuse(answer: Fetched) -> LibraryRefusal:
    """The refusal a failed GitHub read becomes."""
    if answer.outcome is FetchOutcome.NOT_FOUND:
        return LibraryRefusal(NOT_FOUND)
    if answer.outcome is FetchOutcome.RATE_LIMITED:
        return LibraryRefusal(RATE_LIMITED, reset_at=answer.reset_at)
    if answer.outcome is FetchOutcome.TOO_LARGE:
        return LibraryRefusal(TOO_LARGE)
    return LibraryRefusal(UNREACHABLE)


def valid_ref(ref: str) -> bool:
    """Whether ``ref`` reads as a branch or tag name (or ``HEAD``)."""
    return bool(_REF_RE.match(ref)) and ".." not in ref


def valid_repository(repository: str) -> bool:
    """Whether ``repository`` reads as ``owner/repo`` on GitHub."""
    owner, _, repo = repository.partition("/")
    return bool(_OWNER_RE.match(owner) and _REPO_RE.match(repo)) and repo not in {".", ".."}


def safe_relative(path: str) -> bool:
    """Whether a listed path stays inside its folder on every filesystem."""
    if not path or path.startswith("/") or "\\" in path or "\x00" in path or ":" in path:
        return False
    return all(part not in {"", ".", ".."} for part in path.split("/"))


_GITHUB_HOSTS: Final = frozenset({"github.com", "www.github.com"})


def _address_parts(address: str) -> list[str]:
    """The path segments of ``owner/repo...`` or of an https github.com URL.

    Raises:
        LibraryRefusal: ``skill_library_source_invalid`` for any other address.
    """
    text = address.strip()
    if "://" in text:
        parsed = urlparse(text)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _GITHUB_HOSTS:
            raise LibraryRefusal(SOURCE_INVALID)
        text = parsed.path
    return [part for part in text.strip("/").split("/") if part]


def _ref_and_folder(kind: str, rest: list[str]) -> tuple[str, str | None]:
    """The ref and the folder a ``/tree/`` or ``/blob/`` address names.

    A ``blob`` address pointing at a ``SKILL.md`` names the folder holding it.

    Raises:
        LibraryRefusal: ``skill_library_source_invalid`` for an unusable ref or path.
    """
    ref, path = rest[0], "/".join(rest[1:])
    if kind == "blob" and posixpath.basename(path) == _MANIFEST:
        path = posixpath.dirname(path)
    if not valid_ref(ref) or (path and not safe_relative(path)):
        raise LibraryRefusal(SOURCE_INVALID)
    return ref, path or None


def parse_address(address: str) -> GithubAddress:
    """Read ``owner/repo`` or a github.com URL (``/tree/<ref>/<path>`` included).

    Args:
        address: What the person pasted.

    Returns:
        The repository, and the ref and folder when the address names them.

    Raises:
        LibraryRefusal: ``skill_library_source_invalid`` when it names no repository.
    """
    parts = _address_parts(address)
    if len(parts) < 2:
        raise LibraryRefusal(SOURCE_INVALID)
    repository = f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if not valid_repository(repository):
        raise LibraryRefusal(SOURCE_INVALID)
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref, path = _ref_and_folder(parts[2], parts[3:])
        return GithubAddress(repository, ref, path)
    return GithubAddress(repository)


def _api_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.skill_library_github_token:
        headers["Authorization"] = f"Bearer {settings.skill_library_github_token}"
    return headers


async def resolve_commit(client: httpx.AsyncClient, repository: str, ref: str) -> str:
    """The commit ``ref`` points at now (cached briefly: a branch moves).

    Raises:
        LibraryRefusal: When the repository or the ref does not exist, or GitHub
            cannot be read.
    """
    if not valid_ref(ref):
        raise LibraryRefusal(SOURCE_INVALID)
    key = cache.cache_key("head", repository, ref)
    known = await cache.cached(key)
    if isinstance(known, str) and _SHA_RE.match(known):
        return known
    url = f"{SKILL_LIBRARY_GITHUB_API_URL}/repos/{repository}/commits/{quote(ref, safe='')}"
    answer = await fetch(
        client, url, headers={**_api_headers(), "Accept": "application/vnd.github.sha"}
    )
    if answer.outcome is not FetchOutcome.OK:
        raise _refuse(answer)
    sha = answer.body.decode("ascii", "replace").strip()
    if not _SHA_RE.match(sha):
        raise LibraryRefusal(UNREACHABLE)
    await cache.store(key, sha, settings.skill_library_cache_ttl_seconds)
    return sha


async def read_tree(client: httpx.AsyncClient, repository: str, tree_ish: str) -> dict[str, Any]:
    """The recursive listing at a commit or a tree SHA (immutable: cached for the day).

    Raises:
        LibraryRefusal: ``skill_library_too_large`` when GitHub truncated the
            listing — a folder it left out cannot be verified.
    """
    key = cache.cache_key("tree", repository, tree_ish)
    known = await cache.cached(key)
    if isinstance(known, dict):
        return known
    url = f"{SKILL_LIBRARY_GITHUB_API_URL}/repos/{repository}/git/trees/{tree_ish}?recursive=1"
    answer = await fetch(client, url, headers=_api_headers())
    if answer.outcome is not FetchOutcome.OK:
        raise _refuse(answer)
    try:
        listing = json.loads(answer.body)
    except ValueError as exc:
        raise LibraryRefusal(UNREACHABLE) from exc
    if not isinstance(listing, dict) or not isinstance(listing.get("tree"), list):
        raise LibraryRefusal(UNREACHABLE)
    if listing.get("truncated"):
        raise LibraryRefusal(TOO_LARGE)
    kept = {"sha": str(listing.get("sha", "")), "tree": listing["tree"]}
    await cache.store(key, kept, SKILL_LIBRARY_TREE_CACHE_TTL_SECONDS)
    return kept


def skill_folders(listing: dict[str, Any]) -> list[str]:
    """Every folder of the listing that holds a SKILL.md ('' = the root)."""
    folders = [
        posixpath.dirname(entry["path"])
        for entry in listing["tree"]
        if isinstance(entry, dict)
        and entry.get("type") == "blob"
        and posixpath.basename(str(entry.get("path", ""))) == _MANIFEST
        and safe_relative(str(entry.get("path", "")))
    ]
    return sorted(set(folders))


def folder_tree_sha(listing: dict[str, Any], path: str) -> str:
    """The git tree SHA of the folder ``path`` in a listing ('' when absent).

    The root folder is the listing itself.
    """
    if not path:
        return str(listing.get("sha", ""))
    return next(
        (
            str(entry.get("sha", ""))
            for entry in listing["tree"]
            if isinstance(entry, dict) and entry.get("path") == path and entry.get("type") == "tree"
        ),
        "",
    )


def _folder_entries(listing: dict[str, Any], path: str) -> tuple[list[RepoFile], list[str]]:
    """The regular files under ``path``, and the links and submodules never followed."""
    prefix = f"{path}/" if path else ""
    files: list[RepoFile] = []
    skipped: list[str] = []
    for entry in listing["tree"]:
        full = str(entry.get("path", "")) if isinstance(entry, dict) else ""
        if not full.startswith(prefix) or not safe_relative(full):
            continue
        relative = full[len(prefix) :]
        if entry.get("type") == "commit" or entry.get("mode") == _SYMLINK_MODE:
            skipped.append(relative)
        elif entry.get("type") == "blob":
            files.append(RepoFile(relative, int(entry.get("size") or 0), str(entry.get("sha", ""))))
    return files, skipped


def folder_of(
    listing: dict[str, Any], repository: str, ref: str, commit_sha: str, path: str
) -> SkillFolder:
    """The folder ``path`` of a listing: its tree SHA, its files, what is skipped.

    Raises:
        LibraryRefusal: ``skill_library_not_found`` when the folder holds no SKILL.md.
    """
    tree_sha = folder_tree_sha(listing, path)
    files, skipped = _folder_entries(listing, path)
    if not tree_sha or all(f.path != _MANIFEST for f in files):
        raise LibraryRefusal(NOT_FOUND)
    return SkillFolder(
        repository, ref, commit_sha, path, tree_sha, tuple(files), tuple(sorted(skipped))
    )


def blob_sha(data: bytes) -> str:
    """Git's identity of a file: ``sha1("blob <size>\\0" + bytes)``."""
    return hashlib.sha1(b"blob %d\x00" % len(data) + data, usedforsecurity=False).hexdigest()


async def read_file(
    client: httpx.AsyncClient, repository: str, commit_sha: str, full_path: str, sha: str
) -> bytes:
    """One file at a commit, verified against the blob SHA the listing gave.

    Raises:
        LibraryRefusal: When it cannot be read, or its bytes are not the ones listed.
    """
    url = (
        f"{SKILL_LIBRARY_GITHUB_RAW_URL}/{repository}/{commit_sha}/" f"{quote(full_path, safe='/')}"
    )
    answer = await fetch(client, url)
    if answer.outcome is not FetchOutcome.OK:
        raise _refuse(answer)
    if blob_sha(answer.body) != sha:
        raise LibraryRefusal(UNREACHABLE)
    return answer.body
