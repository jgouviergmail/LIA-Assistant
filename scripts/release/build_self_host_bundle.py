"""Deterministic allowlisted self-host bundle (ADR-215, B05).

The bundle ships every read-only runtime asset a prebuilt install
bind-mounts, plus the installer package and the embedded source-context
archive. Determinism contract: sorted member order, uid/gid 0, empty owner
names, mtime 0, mode derived only from the executable bit, gzip mtime 0 —
two builds of the same tree are byte-identical, so the manifest hashes are
reproducible evidence, not snapshots.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Fixed single files every bundle must contain.
BUNDLE_FILES: tuple[str, ...] = (
    "install.sh",
    ".env.min.prod.example",
    "docker-compose.prod.yml",
    "docker-compose.skill-sandbox.yml",
    "infrastructure/caddy/Caddyfile.template",
    "infrastructure/docker/postgres-init.sql",
    "LICENSE",
)

#: Directory roots included recursively (files only, sorted).
BUNDLE_DIRS: tuple[str, ...] = (
    "scripts/install",
    "infrastructure/database/seeds",
    "infrastructure/observability",
    "data/skills/system",
    "docs/knowledge",
    # Per-alert runbooks: docker-compose.prod.yml mounts ./docs/runbooks read-only
    # into the API for the diagnostician (ADR-266). Without them the mount is an
    # empty directory and every diagnosis carries had_runbook=false.
    "docs/runbooks",
)

#: Sub-paths excluded from the production bundle (tests never ship).
BUNDLE_EXCLUDES: tuple[str, ...] = (
    "scripts/install/tests",
    "scripts/install/tests_py310.py",
)

#: Never archived, wherever they appear.
ALWAYS_EXCLUDED_PARTS = ("__pycache__",)
ALWAYS_EXCLUDED_SUFFIXES = (".pyc", ".pyo")

#: Generated member name of the embedded source context inside the bundle.
SOURCE_CONTEXT_MEMBER = "lia-self-host-source-context.tar.gz"


class BundleError(ValueError):
    """A structural bundle problem (missing path, symlink, escape)."""


@dataclass(frozen=True)
class BundleDigests:
    """Archive + canonical-tree SHA-256 pair recorded by the manifest."""

    archive_sha256: str
    tree_sha256: str


def _is_excluded(rel: str) -> bool:
    if any(part in rel.split("/") for part in ALWAYS_EXCLUDED_PARTS):
        return True
    if rel.endswith(ALWAYS_EXCLUDED_SUFFIXES):
        return True
    return any(
        rel == excluded or rel.startswith(excluded + "/")
        for excluded in BUNDLE_EXCLUDES
    )


def iter_bundle_files(root: Path) -> Iterator[str]:
    """Yield the sorted repo-relative bundle inventory present under root.

    Non-strict by design: unit tests inspect partial trees, and the first
    complete live build (Task 15 checkpoint) goes through
    :func:`build_archive`, which fails closed on any missing path.
    """
    collected: set[str] = set()
    for fixed in BUNDLE_FILES:
        if (root / fixed).is_file():
            collected.add(fixed)
    for directory in BUNDLE_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if not _is_excluded(rel):
                collected.add(rel)
    yield from sorted(collected)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tree_digest(root: Path, files: Collection[str]) -> str:
    digest = hashlib.sha256()
    for rel in sorted(files):
        target = root / rel
        executable = "x" if (target.stat().st_mode & 0o100) else "-"
        digest.update(rel.encode("utf-8") + b"\0" + executable.encode("ascii"))
        digest.update(hashlib.sha256(target.read_bytes()).digest() + b"\n")
    return digest.hexdigest()


def build_archive(
    root: Path,
    files: Collection[str],
    output: Path,
    *,
    extra_members: dict[str, bytes] | None = None,
) -> BundleDigests:
    """Build the deterministic tar.gz for an explicit file list.

    Args:
        root: Tree the relative paths resolve against.
        files: Repo-relative POSIX paths to include (validated, no symlink,
            no escape, all present).
        output: Destination archive path.
        extra_members: Optional generated members (name → bytes), e.g. the
            embedded source-context archive.

    Returns:
        The archive and canonical-tree digests.

    Raises:
        BundleError: On a missing path, symlink, or root escape.
    """
    resolved_root = root.resolve()
    ordered = sorted(set(files))
    for rel in ordered:
        target = root / rel
        if target.is_symlink():
            raise BundleError(f"symlink refused in bundle: {rel}")
        if not target.is_file():
            raise BundleError(f"missing bundled path: {rel}")
        if resolved_root not in target.resolve().parents and target.resolve() != resolved_root:
            raise BundleError(f"path escapes the bundle root: {rel}")
        if _is_excluded(rel):
            raise BundleError(f"excluded path explicitly listed: {rel}")

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        member_names = list(ordered)
        generated = dict(sorted((extra_members or {}).items()))
        for name in generated:
            member_names.append(name)
        for rel in sorted(member_names):
            info = tarfile.TarInfo(name=rel)
            if rel in generated:
                data = generated[rel]
                info.mode = 0o644
            else:
                target = root / rel
                data = target.read_bytes()
                info.mode = 0o755 if (target.stat().st_mode & 0o100) else 0o644
            info.size = len(data)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))

    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as gz:
        gz.write(buffer.getvalue())
    payload = compressed.getvalue()
    output.write_bytes(payload)
    return BundleDigests(
        archive_sha256=_hash_bytes(payload),
        tree_sha256=_tree_digest(root, ordered),
    )


def build_bundle(
    root: Path, source_context_archive: Path, output: Path
) -> BundleDigests:
    """Build the complete live host bundle (fail-closed on missing paths).

    Args:
        root: Repository root.
        source_context_archive: The already-built deterministic source
            context to embed as ``lia-self-host-source-context.tar.gz``.
        output: Destination bundle path.

    Returns:
        The bundle digests for the candidate manifest.
    """
    files = list(iter_bundle_files(root))
    for fixed in BUNDLE_FILES:
        if fixed not in files:
            raise BundleError(f"missing bundled path: {fixed}")
    return build_archive(
        root,
        files,
        output,
        extra_members={
            SOURCE_CONTEXT_MEMBER: source_context_archive.read_bytes()
        },
    )
