"""Portable monorepo-root discovery for repository guard tests.

Guard tests that inspect repo-root artifacts (``Taskfile.yml``, ``Makefile``,
``.github/``, ``docs/``, cross-app files) historically hardcoded
``Path(__file__).resolve().parents[4]`` to reach the repository root. That
fixed-depth assumption breaks the moment the tree is checked out at a
different depth or bind-mounted flat: the dev container mounts only
``apps/api`` at ``/app``, so ``parents[4]`` raises ``IndexError`` at *collection*
time (audit finding F050) and takes the whole module down.

This module discovers roots by walking up from a known in-tree anchor looking
for stable *sentinels*, honours an explicit ``LIA_REPO_ROOT`` override for flat
mounts, and raises an actionable error otherwise. It never falls back to the
current working directory (which would silently pass/fail depending on where
pytest happens to be launched).

Two roots are exposed:

* :func:`find_repo_root` / :func:`repo_root_or_skip` — the *monorepo* root
  (contains ``Taskfile.yml`` + ``apps/api/pyproject.toml``). Repo-level guards
  that read root-only artifacts skip cleanly when it is unavailable.
* :func:`find_apps_api_root` — the ``apps/api`` package root (contains
  ``src/main.py`` + ``pyproject.toml``); always present under the ``/app`` mount.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT_ENV_VAR = "LIA_REPO_ROOT"

# Sentinels that JOINTLY identify a directory as the monorepo root. Both must
# exist: ``apps/api/pyproject.toml`` alone also resolves one level down (inside
# apps/api itself), and ``Taskfile.yml`` alone is absent from a flat apps/api
# mount — requiring both removes every ambiguity.
_REPO_SENTINELS = ("Taskfile.yml", "apps/api/pyproject.toml")

# Sentinels that identify the ``apps/api`` package root (present even under the
# flat ``/app`` bind mount).
_APPS_API_SENTINELS = ("pyproject.toml", "src/main.py")


class RepoRootNotFound(RuntimeError):
    """Raised when a required repository root cannot be located."""


def _has_all(candidate: Path, sentinels: tuple[str, ...]) -> bool:
    return candidate.is_dir() and all((candidate / rel).exists() for rel in sentinels)


def _walk_up(anchor: Path, sentinels: tuple[str, ...]) -> Path | None:
    """Return the first ancestor of ``anchor`` (inclusive) matching sentinels."""
    resolved = anchor.resolve()
    for candidate in (resolved, *resolved.parents):
        if _has_all(candidate, sentinels):
            return candidate
    return None


def find_repo_root(start: Path | None = None, *, required: bool = True) -> Path | None:
    """Locate the monorepo root without assuming a fixed checkout depth.

    Resolution order:
        1. ``LIA_REPO_ROOT`` environment variable (for flat/bind-mounted
           layouts), validated against the sentinels.
        2. Walk parents of ``start`` (default: this module's location, so
           discovery is independent of the current working directory) looking
           for a directory that contains every sentinel.

    Args:
        start: Directory/file to begin the upward walk from. Defaults to this
            module's location.
        required: When True (default), raise :class:`RepoRootNotFound` if the
            root cannot be located; when False, return ``None`` instead.

    Returns:
        The resolved repository root, or ``None`` when ``required`` is False and
        the root is not found.

    Raises:
        RepoRootNotFound: When ``required`` is True and no root is found.
    """
    # Literal key on purpose (== REPO_ROOT_ENV_VAR): the pre-commit
    # .env.example-completeness scanner reads the identifier passed to
    # environ.get, so an indirected constant registers a phantom variable.
    override = os.environ.get("LIA_REPO_ROOT")
    if override:
        candidate = Path(override).resolve()
        if _has_all(candidate, _REPO_SENTINELS):
            return candidate
        if required:
            raise RepoRootNotFound(
                f"{REPO_ROOT_ENV_VAR}={override!r} does not point at a monorepo root "
                f"(expected all of {_REPO_SENTINELS})."
            )
        return None

    anchor = start or Path(__file__)
    root = _walk_up(anchor, _REPO_SENTINELS)
    if root is not None:
        return root

    if required:
        raise RepoRootNotFound(
            "Monorepo root not found by walking up from "
            f"{Path(anchor).resolve()} (looking for {_REPO_SENTINELS}). This usually "
            "means the tree is bind-mounted flat (e.g. apps/api at /app). Set "
            f"{REPO_ROOT_ENV_VAR} to the repository root to run repo-level guards here."
        )
    return None


def repo_root_or_skip(start: Path | None = None) -> Path:
    """Return the monorepo root, or skip the current module when it is absent.

    Repo-level guards inspect artifacts that only exist in a full checkout
    (``Taskfile.yml``, ``Makefile``, ``.github/``, ``docs/``). Under a flat
    ``apps/api`` mount those files are absent, so the guard cannot run — it is
    skipped with an actionable message rather than erroring at collection.
    """
    import pytest

    root = find_repo_root(start, required=False)
    if root is None:
        pytest.skip(
            "monorepo root not found (flat apps/api mount?); set "
            f"{REPO_ROOT_ENV_VAR} to run repo-level guards here",
            allow_module_level=True,
        )
    return root


def find_apps_api_root(start: Path | None = None) -> Path:
    """Locate the ``apps/api`` package root (present even under the /app mount).

    Args:
        start: Directory/file to begin the upward walk from. Defaults to this
            module's location.

    Returns:
        The resolved ``apps/api`` root directory.

    Raises:
        RepoRootNotFound: When the package root cannot be located.
    """
    anchor = start or Path(__file__)
    root = _walk_up(anchor, _APPS_API_SENTINELS)
    if root is None:
        raise RepoRootNotFound(
            "apps/api root not found by walking up from "
            f"{Path(anchor).resolve()} (looking for {_APPS_API_SENTINELS})."
        )
    return root
