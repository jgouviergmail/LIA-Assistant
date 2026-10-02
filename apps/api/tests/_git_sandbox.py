"""Git commands for the throwaway repositories tests build, isolated from the caller's.

Git exports repository-local variables (``GIT_DIR``, ``GIT_INDEX_FILE``,
``GIT_WORK_TREE``…) to the commands its hooks run. Inherited, they send a test's
``git -C <tmp> init`` / ``config`` / ``commit`` into the repository the test runs in:
that is how the real ``.git/config`` came to hold the test identity
``guard <guard@example.test>`` (found 2026-10-02). The pre-commit hook clears those
variables since ``354484ed``; this module clears them where the test runs, whatever
launched it.
"""

from __future__ import annotations

import os
import subprocess
from functools import cache
from pathlib import Path


@cache
def _repository_local_variables() -> frozenset[str]:
    """The variable names git itself declares local to a repository."""
    listed = subprocess.run(
        ["git", "rev-parse", "--local-env-vars"], check=True, capture_output=True, text=True
    )
    return frozenset(listed.stdout.split())


def isolated_git_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """The current environment without any repository-local git variable.

    Args:
        overrides: Variables to set on top (an author identity, say).

    Returns:
        An environment for a git subprocess that can only reach the repository it names.
    """
    local = _repository_local_variables()
    return {
        **{name: value for name, value in os.environ.items() if name not in local},
        **(overrides or {}),
    }


def run_git(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run one git command in ``root``, isolated from the caller's repository.

    Args:
        root: The throwaway repository (or the directory to create it in).
        *args: The git command and its arguments.
        env: Variables to set on top of the isolated environment.

    Returns:
        The completed process, its output captured as text.

    Raises:
        subprocess.CalledProcessError: The command failed.
    """
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        env=isolated_git_env(env),
    )
