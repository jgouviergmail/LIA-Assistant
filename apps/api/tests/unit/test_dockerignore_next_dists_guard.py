"""Every Next.js dist the repository ignores stays out of the Docker build context (audit A03).

Both web images build from the repository root, so a dist under ``apps/web``
enters their context unless ``.dockerignore`` excludes it. Proof runs write their
dists as ``.next-<name>`` (``NEXT_DIST_DIR``; ``capture_public_screenshots.ps1``
accepts ``^\\.next-[a-zA-Z0-9-]+$``): ``.dockerignore`` excluded ``.next-e2e*``
alone, and ``.next-public-screenshots`` entered every web build. What git keeps
out of the repository, Docker keeps out of the context.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
GITIGNORES = (REPO_ROOT / ".gitignore", REPO_ROOT / "apps" / "web" / ".gitignore")


def _patterns(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def _next_dists_git_ignores() -> set[str]:
    """Each Next.js dist pattern a ``.gitignore`` names, as a bare directory pattern."""
    return {
        pattern.strip("/")
        for gitignore in GITIGNORES
        for pattern in _patterns(gitignore)
        if pattern.strip("/").startswith(".next")
    }


def test_every_next_dist_git_ignores_is_out_of_the_build_context() -> None:
    dists = _next_dists_git_ignores()
    docker = set(_patterns(REPO_ROOT / ".dockerignore"))

    assert {".next", ".next-*"} <= dists, "the .gitignore files no longer name the dists"
    missing = sorted(dist for dist in dists if f"**/{dist}" not in docker)
    assert not missing, f".dockerignore lets these dists into the web build context: {missing}"


def test_every_dist_the_screenshot_capture_accepts_is_excluded() -> None:
    script = (REPO_ROOT / "scripts" / "capture_public_screenshots.ps1").read_text(encoding="utf-8")
    accepted = re.search(r"ValidatePattern\('([^']+)'\)", script)
    assert accepted is not None, "the capture script no longer validates its dist name"
    default = re.search(r"\$DistDirectory = '([^']+)'", script)
    assert default is not None and re.fullmatch(accepted.group(1), default.group(1))

    assert accepted.group(1).startswith(r"^\.next-")
    assert fnmatch.fnmatch(default.group(1), ".next-*")
