"""A throwaway git repository a test builds never reaches the repository it runs in.

Git exports repository-local variables (``GIT_DIR``, ``GIT_INDEX_FILE``…) to the
commands its hooks run. A test that inherits them and runs ``git -C <tmp> init`` creates
nothing in ``<tmp>``: the init, the config and the commits all land in the inherited
repository. Measured: that is how the real ``.git/config`` came to hold the test identity
``guard <guard@example.test>``, and how every commit from 2026-09-28 to 2026-10-02 was
authored by it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._git_sandbox import isolated_git_env, run_git

pytestmark = pytest.mark.unit


def test_an_inherited_repository_is_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outer = tmp_path / "outer"
    subprocess.run(
        ["git", "init", "-q", str(outer)], check=True, capture_output=True, env=isolated_git_env()
    )
    before = (outer / ".git" / "config").read_text(encoding="utf-8")
    # What a git hook hands the commands it runs.
    monkeypatch.setenv("GIT_DIR", str(outer / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(outer / ".git" / "index"))
    inner = tmp_path / "inner"
    inner.mkdir()

    run_git(inner, "init", "-q")
    run_git(inner, "config", "user.name", "guard")

    assert (outer / ".git" / "config").read_text(encoding="utf-8") == before
    assert "guard" in (inner / ".git" / "config").read_text(encoding="utf-8")


def test_a_caller_s_overrides_still_reach_git(tmp_path: Path) -> None:
    run_git(tmp_path, "init", "-q")

    name = run_git(tmp_path, "var", "GIT_AUTHOR_IDENT", env={"GIT_AUTHOR_NAME": "probe"})

    assert name.stdout.startswith("probe ")
