"""Deterministic host bundle + embedded source context (B05).

What must hold:
- two builds from the same fixture tree produce byte-identical archives
  (sorted paths, uid/gid 0, empty owner names, mtime 0, gzip mtime 0);
- symlinks and paths resolving outside the root are rejected;
- `__pycache__`, `.pyc`, `.pyo` never enter an archive even when present;
- the production bundle excludes installer tests; the source context
  excludes `.git`, env files, node_modules, virtualenvs, and caches;
- the source-context inventory is anchored to the Dockerfiles' COPY
  sources — a new build-context COPY fails until the inventory is reviewed;
- archive and canonical-tree SHA-256 pairs are returned for the manifest.
"""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.build_self_host_bundle import (  # noqa: E402
    BundleDigests,
    BundleError,
    build_archive,
    iter_bundle_files,
)
from scripts.release.build_self_host_source_context import (  # noqa: E402
    SOURCE_CONTEXT_ROOTS,
    dockerfile_copy_sources,
)

pytestmark = pytest.mark.unit


def _make_fixture(root: Path) -> list[str]:
    (root / "scripts/install").mkdir(parents=True)
    (root / "scripts/install/__init__.py").write_text("", encoding="utf-8")
    (root / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    # Pollution that must never enter an archive:
    (root / "scripts/install/__pycache__").mkdir()
    (root / "scripts/install/__pycache__/x.cpython-312.pyc").write_bytes(b"junk")
    return ["install.sh", "LICENSE", "scripts/install/__init__.py"]


def test_two_builds_are_byte_identical(tmp_path: Path) -> None:
    files = _make_fixture(tmp_path / "src")
    out1 = tmp_path / "a.tar.gz"
    out2 = tmp_path / "b.tar.gz"
    d1 = build_archive(tmp_path / "src", files, out1)
    d2 = build_archive(tmp_path / "src", files, out2)
    assert isinstance(d1, BundleDigests)
    assert out1.read_bytes() == out2.read_bytes()
    assert d1 == d2
    assert len(d1.archive_sha256) == 64
    assert len(d1.tree_sha256) == 64


def test_archive_members_are_normalized(tmp_path: Path) -> None:
    files = _make_fixture(tmp_path / "src")
    out = tmp_path / "a.tar.gz"
    build_archive(tmp_path / "src", files, out)
    with tarfile.open(fileobj=io.BytesIO(out.read_bytes()), mode="r:gz") as tar:
        names = tar.getnames()
        assert names == sorted(names)
        for member in tar.getmembers():
            assert member.uid == 0 and member.gid == 0
            assert member.uname == "" and member.gname == ""
            assert member.mtime == 0
            assert "__pycache__" not in member.name
            assert not member.name.endswith((".pyc", ".pyo"))


def test_symlink_is_rejected(tmp_path: Path) -> None:
    files = _make_fixture(tmp_path / "src")
    link = tmp_path / "src" / "evil"
    try:
        link.symlink_to(tmp_path / "src" / "LICENSE")
    except OSError:
        pytest.skip("symlinks unavailable on this host")
    with pytest.raises(BundleError, match="symlink"):
        build_archive(tmp_path / "src", [*files, "evil"], tmp_path / "a.tar.gz")


def test_missing_allowlisted_path_fails_closed(tmp_path: Path) -> None:
    files = _make_fixture(tmp_path / "src")
    with pytest.raises(BundleError, match="missing"):
        build_archive(
            tmp_path / "src", [*files, "does/not/exist.txt"], tmp_path / "a.tar.gz"
        )


def test_live_bundle_inventory_excludes_tests_and_bytecode() -> None:
    files = list(iter_bundle_files(REPO_ROOT))
    joined = "\n".join(files)
    # install.sh / Caddyfile.template arrive with the wizard tasks; the
    # complete-live-build checkpoint (build_bundle) fails closed on them.
    assert "docker-compose.prod.yml" in files
    assert "docker-compose.skill-sandbox.yml" in files
    assert ".env.min.prod.example" in files
    assert "infrastructure/docker/postgres-init.sql" in files
    assert "scripts/install/manifest.py" in files
    assert "scripts/install/tests" not in joined
    assert "__pycache__" not in joined
    assert ".pyc" not in joined
    assert "docker-compose.devops.yml" not in files  # maintainer-only overlay


def test_source_context_inventory_covers_every_dockerfile_copy() -> None:
    copies = dockerfile_copy_sources(REPO_ROOT)
    assert copies, "the Dockerfiles must declare COPY build inputs"
    for source in copies:
        covered = any(
            source == root or source.startswith(root.rstrip("/") + "/")
            for root in SOURCE_CONTEXT_ROOTS
        )
        assert covered, (
            f"Dockerfile COPY source {source!r} is not covered by "
            "SOURCE_CONTEXT_ROOTS — review the inventory before shipping"
        )


def test_source_context_roots_exclude_secret_and_cache_material() -> None:
    for root in SOURCE_CONTEXT_ROOTS:
        assert ".git" not in root
        assert "node_modules" not in root
        assert ".venv" not in root
        assert not root.startswith(".env")
