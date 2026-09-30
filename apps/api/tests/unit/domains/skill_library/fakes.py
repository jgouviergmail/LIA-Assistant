"""A fake skills.sh and a fake GitHub, served through ``httpx.MockTransport`` (ADR-327).

The fake speaks the REAL contracts the library reads: ``/api/search`` and the
audit route of the portal, ``commits/{ref}`` with the ``vnd.github.sha``
answer, ``git/trees/{sha}?recursive=1`` with ``truncated``, and raw files at
``{owner}/{repo}/{commit}/{path}``. Blob SHAs are git's own
(``sha1("blob <size>\\0" + bytes)``) so a verification the library makes here
is the verification it makes against GitHub; a folder's tree SHA changes when
anything under it changes, like git's.

Every request is recorded with the host it was ADDRESSED to (the pinned
request carries it in ``Host``), and with its headers, so a test can prove
where a credential went.
"""

from __future__ import annotations

import hashlib
import posixpath
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, unquote

import httpx

from src.domains.skill_library.github import blob_sha


def _tree_sha(files: dict[str, bytes], folder: str) -> str:
    prefix = f"{folder}/" if folder else ""
    lines = sorted(
        f"{path[len(prefix):]}:{blob_sha(data)}"
        for path, data in files.items()
        if path.startswith(prefix)
    )
    return hashlib.sha1("\n".join(lines).encode(), usedforsecurity=False).hexdigest()


def commit_sha(label: str) -> str:
    """A stable 40-hex commit id for a label."""
    return hashlib.sha1(label.encode(), usedforsecurity=False).hexdigest()


def manifest(name: str, description: str = "Does things.") -> bytes:
    """A minimal valid SKILL.md."""
    return f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nBody.\n".encode()


@dataclass
class Seen:
    """One request the fake answered."""

    host: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]


@dataclass
class FakeHub:
    """Repositories, branch heads, portal results and audits — and what was asked."""

    commits: dict[tuple[str, str], dict[str, bytes]] = field(default_factory=dict)
    heads: dict[tuple[str, str], str] = field(default_factory=dict)
    extra_entries: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    search_results: list[dict[str, Any]] = field(default_factory=list)
    audits: dict[str, Any] | None = field(default_factory=dict)
    truncated: bool = False
    corrupt: set[str] = field(default_factory=set)
    rate_limited: bool = False
    seen: list[Seen] = field(default_factory=list)

    def publish(
        self, repository: str, label: str, files: dict[str, bytes], ref: str = "HEAD"
    ) -> str:
        """Commit ``files`` to ``repository`` and point ``ref`` at it."""
        sha = commit_sha(f"{repository}@{label}")
        self.commits[(repository, sha)] = dict(files)
        self.heads[(repository, ref)] = sha
        return sha

    def tree_sha(self, repository: str, commit: str, folder: str) -> str:
        """The folder's tree SHA at a commit, as the listing gives it."""
        return _tree_sha(self.commits[(repository, commit)], folder)

    # --- listing ---------------------------------------------------------

    def _listing(self, repository: str, tree_ish: str) -> dict[str, Any] | None:
        if (repository, tree_ish) in self.commits:
            files, root = self.commits[(repository, tree_ish)], ""
        else:
            found = self._folder_by_tree_sha(repository, tree_ish)
            if found is None:
                return None
            files, root = found
        prefix = f"{root}/" if root else ""
        scoped = {p[len(prefix) :]: d for p, d in files.items() if p.startswith(prefix)}
        folders = {posixpath.dirname(p) for p in scoped if posixpath.dirname(p)}
        expanded = set()
        for folder in folders:
            parts = folder.split("/")
            expanded.update("/".join(parts[: i + 1]) for i in range(len(parts)))
        tree: list[dict[str, Any]] = [
            {"path": f, "mode": "040000", "type": "tree", "sha": _tree_sha(scoped, f)}
            for f in sorted(expanded)
        ]
        tree += [
            {"path": p, "mode": "100644", "type": "blob", "sha": blob_sha(d), "size": len(d)}
            for p, d in sorted(scoped.items())
        ]
        tree += self.extra_entries.get((repository, tree_ish), [])
        return {"sha": _tree_sha(scoped, ""), "tree": tree, "truncated": self.truncated}

    def _folder_by_tree_sha(self, repository: str, sha: str) -> tuple[dict[str, bytes], str] | None:
        for (repo, _), files in self.commits.items():
            if repo != repository:
                continue
            folders = {""} | {posixpath.dirname(p) for p in files}
            for folder in folders:
                if _tree_sha(files, folder) == sha:
                    return files, folder
        return None

    # --- transport -------------------------------------------------------

    def handler(self, request: httpx.Request) -> httpx.Response:
        host = request.headers.get("host", request.url.host)
        path = unquote(request.url.path)
        self.seen.append(
            Seen(host, path, parse_qs(request.url.query.decode()), dict(request.headers))
        )
        if self.rate_limited and host == "api.github.com":
            return httpx.Response(
                403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1900000000"}
            )
        if host == "skills.sh" and path == "/api/search":
            return httpx.Response(200, json={"skills": self.search_results})
        if host == "add-skill.vercel.sh" and path == "/audit":
            if self.audits is None:
                return httpx.Response(503)
            return httpx.Response(200, json=self.audits)
        if host == "api.github.com":
            return self._api(path)
        if host == "raw.githubusercontent.com":
            return self._raw(path)
        return httpx.Response(404)

    def _api(self, path: str) -> httpx.Response:
        parts = path.strip("/").split("/")
        if len(parts) >= 5 and parts[0] == "repos" and parts[3] == "commits":
            repository, ref = f"{parts[1]}/{parts[2]}", "/".join(parts[4:])
            sha = self.heads.get((repository, ref))
            return httpx.Response(200, text=sha) if sha else httpx.Response(404)
        if len(parts) == 6 and parts[0] == "repos" and parts[3:5] == ["git", "trees"]:
            listing = self._listing(f"{parts[1]}/{parts[2]}", parts[5])
            return httpx.Response(200, json=listing) if listing else httpx.Response(404)
        return httpx.Response(404)

    def _raw(self, path: str) -> httpx.Response:
        owner, repo, sha, *rest = path.strip("/").split("/")
        files = self.commits.get((f"{owner}/{repo}", sha))
        name = "/".join(rest)
        if files is None or name not in files:
            return httpx.Response(404)
        data = files[name]
        return httpx.Response(200, content=data + b"!" if name in self.corrupt else data)

    def client(self) -> httpx.AsyncClient:
        """A client whose every request this fake answers."""
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    def hosts(self) -> list[str]:
        """The hosts asked, in order."""
        return [s.host for s in self.seen]


def entry(repository: str, skill_id: str, installs: int = 10) -> dict[str, Any]:
    """A skills.sh search result for a GitHub skill."""
    return {
        "id": f"{repository}/{skill_id}",
        "source": repository,
        "skillId": skill_id,
        "name": skill_id,
        "installs": installs,
    }


def audit_of(skill_id: str, **risks: str) -> dict[str, Any]:
    """An audit answer: one provider per keyword, with its risk."""
    return {skill_id: {provider: {"risk": risk, "alerts": []} for provider, risk in risks.items()}}
