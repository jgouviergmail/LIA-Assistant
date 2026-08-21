"""Every runtime directory of ``apps/api`` must reach the production image.

The API image is built from the ``apps/api`` context with a blanket
``COPY --chown=appuser:appuser . .``. That instruction is OPAQUE: it names no
path, so the sibling guard ``test_prepare_prod_build_context_guard`` — which
derives its expectations from ``COPY`` sources — cannot see what the image
actually needs. Meanwhile ``scripts/deploy/prepare-prod.ps1`` rebuilds the
PROD/apps/api directory from a hand-kept list, and whatever that list omits is
simply absent from the build context, hence from the image.

Dev never catches it: ``docker-compose.dev.yml`` bind-mounts the whole source
tree (``./apps/api:/app``), so every directory is present locally by
construction. The asymmetry is total — the defect can only exist in production.

Measured in production on 2026-08-05, after a completed deployment::

    docker exec lia-api-prod ls /app/locales  -> No such file or directory

``apps/api/locales`` holds the compiled gettext catalogues for the six supported
languages. Absent, ``core.i18n`` falls back to returning the msgid for every
lookup, in every language, silently.

Rather than restate a whitelist (which is how the omission happened), this guard
enumerates the directories that EXIST in ``apps/api`` and requires each one to be
either copied by the script or explicitly exempt with a written reason. A new
runtime directory therefore fails CI until somebody classifies it.
"""

from __future__ import annotations

import re
import subprocess

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
API_ROOT = REPO_ROOT / "apps" / "api"
PREPARE_SCRIPT = REPO_ROOT / "scripts" / "deploy" / "prepare-prod.ps1"
DOCKERIGNORE = API_ROOT / ".dockerignore"

# Directories that are git-tracked yet legitimately never reach the production
# image, each with the reason.
#
# Currently empty, and that is not an oversight. The scan below considers only
# directories holding git-tracked files, so anything that exists purely as local
# runtime state (``data/``, ``docs/`` — both untracked, both absent from a fresh
# checkout) never reaches the scan and needs no exemption. Listing them here was
# the reverse defect of the one this guard exists to catch: an exemption for a
# path CI never sees is dead weight that fails on the clean checkout it was
# supposed to describe.
#
# Add an entry only for a TRACKED directory the image must not carry.
EXEMPT: dict[str, str] = {}


def _dockerignored_dirs() -> set[str]:
    """Top-level directory names excluded from the build context."""
    if not DOCKERIGNORE.is_file():
        return set()
    ignored: set[str] = set()
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        # Only plain directory names matter here; globs and nested paths are
        # file-level exclusions that never remove a whole runtime directory.
        if "/" in line or "*" in line or "." in line:
            continue
        ignored.add(line)
    return ignored


def _api_source_dirs() -> set[str]:
    """Directories of apps/api that the build context would carry.

    Only directories holding at least one GIT-TRACKED file count. Scanning the
    filesystem alone made this guard fail on local debris: a stray empty tree
    (``apps/api/infrastructure/database/seeds``, left behind by a command run
    from the wrong working directory) reddened the release gate while CI — which
    starts from a checkout, and git stores no empty directories — stayed green.
    A guard whose verdict depends on what happens to sit on a developer's disk
    reports on the developer, not on the build.
    """
    ignored = _dockerignored_dirs()
    listing = subprocess.run(
        ["git", "ls-files", "--", str(API_ROOT)],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout.splitlines()

    prefix = "apps/api/"
    tracked_dirs: set[str] = set()
    for entry in listing:
        relative = entry[len(prefix) :] if entry.startswith(prefix) else entry
        head, separator, _ = relative.partition("/")
        if separator:  # a file at the root of apps/api names no directory
            tracked_dirs.add(head)

    return {name for name in tracked_dirs if not name.startswith(".") and name not in ignored}


def _copied_by_prepare_script() -> set[str]:
    """Directory names the script copies into PROD/apps/api.

    The script joins paths as ``apps\\api\\<name>``; reading those literals is
    what ties the assertion to the deployment's real behaviour.
    """
    body = PREPARE_SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(r'apps\\+api\\+([A-Za-z0-9_-]+)"', body))


class TestApiRuntimeDirectoriesReachTheImage:
    """A runtime directory absent from the build context is absent from prod."""

    def test_every_api_directory_is_copied_or_exempt(self) -> None:
        """New directories must be classified, not silently dropped."""
        copied = _copied_by_prepare_script()
        unclassified = sorted(_api_source_dirs() - copied - set(EXEMPT))

        assert not unclassified, (
            f"apps/api directories neither copied by prepare-prod.ps1 nor exempt: "
            f"{unclassified}. The API image is built with an opaque `COPY . .`, so a "
            f"directory missing from the script is missing from production while dev "
            f"— which bind-mounts the whole tree — stays green. Add it to the script's "
            f"API section, or to EXEMPT here with the reason it is not needed at runtime."
        )

    def test_locales_are_copied(self) -> None:
        """The regression this guard was written for (prod 2026-08-05)."""
        assert "locales" in _copied_by_prepare_script(), (
            "apps/api/locales must be copied: without the compiled gettext catalogues "
            "every backend translation silently degrades to its msgid, in all six languages."
        )

    def test_exempt_entries_are_still_needed(self) -> None:
        """An exemption the scan never consults is stale documentation.

        Checked against what git tracks, not against the local filesystem — the
        same reason the scan is git-aware. Testing ``(API_ROOT / name).is_dir()``
        passed on any developer machine and failed on the CI checkout for the two
        untracked runtime directories that used to be listed here.
        """
        stale = sorted(set(EXEMPT) - _api_source_dirs())

        assert not stale, (
            f"EXEMPT names directories the scan never sees: {stale}. Either they hold no "
            f"git-tracked file (so they cannot reach the build context and need no "
            f"exemption), or they were deleted. Remove the entry."
        )
