"""Deterministic embedded source-build context (ADR-215, B05).

`--local-build` from an official release directory builds the app images
from THIS archive — never from the runtime-only host files and never from
the network. Its inventory is anchored to the effective Docker build inputs:
every non-stage COPY source of `apps/api/Dockerfile.prod` (context
`./apps/api`) and `apps/web/Dockerfile.prod` (context repo root) must be
covered by :data:`SOURCE_CONTEXT_ROOTS`, and a new COPY fails the static
test until the inventory is reviewed. Secrets, caches, bytecode, and VCS
material are excluded by construction.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.release.build_self_host_bundle import (  # noqa: E402
    BundleDigests,
    build_archive,
)

#: Repo-relative roots (files or directories) of the two build contexts.
SOURCE_CONTEXT_ROOTS: tuple[str, ...] = (
    "apps/api",
    "apps/web",
    ".npmrc",
    "pnpm-workspace.yaml",
    "pnpm-lock.yaml",
    "package.json",
    "patches",
)

#: Directory names never archived, wherever they appear.
_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".next",
        ".next-e2e",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "htmlcov",
        "coverage",
        "test-results",
        "playwright-report",
        "config",  # apps/api/config holds deployment credentials (gitignored)
    }
)

_EXCLUDED_SUFFIXES = (".pyc", ".pyo", ".log", ".tsbuildinfo")

_COPY_RE = re.compile(r"^COPY\s+(?!--from=)((?:--\w+(?:=\S+)?\s+)*)(.+)$")


def _split_copy_sources(arguments: str) -> list[str]:
    parts = arguments.split()
    return parts[:-1] if len(parts) > 1 else []


def dockerfile_copy_sources(root: Path) -> list[str]:
    """Resolve every non-stage COPY source to a repo-relative path.

    Args:
        root: Repository root.

    Returns:
        Sorted repo-relative COPY sources of both production Dockerfiles.
    """
    sources: set[str] = set()
    for dockerfile, context in (
        (root / "apps/api/Dockerfile.prod", "apps/api"),
        (root / "apps/web/Dockerfile.prod", ""),
    ):
        for line in dockerfile.read_text(encoding="utf-8").splitlines():
            match = _COPY_RE.match(line.strip())
            if not match:
                continue
            for src in _split_copy_sources(match.group(2)):
                if src.startswith("--"):
                    continue
                relative = src[2:] if src.startswith("./") else src
                relative = relative or "."
                if relative == ".":
                    resolved = context or "."
                else:
                    resolved = f"{context}/{relative}" if context else relative
                sources.add(resolved)
    return sorted(sources)


def _excluded(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in _EXCLUDED_DIR_NAMES for part in parts):
        return True
    if rel.endswith(_EXCLUDED_SUFFIXES):
        return True
    name = parts[-1]
    if name.startswith(".env") and name not in (".env.example", ".env.min.prod"):
        return True
    return False


def iter_source_context_files(root: Path) -> Iterator[str]:
    """Yield the sorted repo-relative source-context inventory."""
    collected: set[str] = set()
    for entry in SOURCE_CONTEXT_ROOTS:
        base = root / entry
        if base.is_file():
            if not _excluded(entry):
                collected.add(entry)
            continue
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(root).as_posix()
            if not _excluded(rel):
                collected.add(rel)
    yield from sorted(collected)


def build_source_context(
    root: Path, output: Path, *, source_sha: str
) -> BundleDigests:
    """Build the deterministic source-context archive.

    Args:
        root: Repository root at the exact release source identity.
        output: Destination archive path.
        source_sha: Full 40-hex source commit recorded in a non-executable
            metadata member (`SOURCE_SHA`).

    Returns:
        The archive/tree digests for the candidate manifest.
    """
    files = list(iter_source_context_files(root))
    return build_archive(
        root,
        files,
        output,
        extra_members={"SOURCE_SHA": (source_sha + "\n").encode("ascii")},
    )
