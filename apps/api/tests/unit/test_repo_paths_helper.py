"""Tests for the portable repo-root discovery helper (audit F050).

Proves the helper locates the monorepo root without a fixed-depth assumption
and across the layouts that broke ``parents[4]``: normal checkout, arbitrary
CWD, symlinked tree, explicit override, and the flat ``apps/api`` bind mount
(where the root is genuinely absent and discovery must fail cleanly rather than
raise ``IndexError`` at collection).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests._repo_paths import (
    REPO_ROOT_ENV_VAR,
    RepoRootNotFound,
    find_apps_api_root,
    find_repo_root,
)


def _make_repo(root: Path) -> Path:
    """Materialize the two monorepo sentinels under ``root``."""
    (root / "apps" / "api").mkdir(parents=True, exist_ok=True)
    (root / "Taskfile.yml").write_text("# sentinel\n", encoding="utf-8")
    (root / "apps" / "api" / "pyproject.toml").write_text("# sentinel\n", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _clear_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let an ambient LIA_REPO_ROOT leak into the walk-up assertions."""
    monkeypatch.delenv(REPO_ROOT_ENV_VAR, raising=False)


class TestFindRepoRoot:
    def test_locates_the_monorepo_root_from_a_nested_anchor(self, tmp_path: Path) -> None:
        # Layout-independent (audit F050 follow-up): the helper must find a
        # sentinel-bearing root from any depth — proven on a constructed tree
        # so the test passes identically on the host and under the flat /app
        # mount (where the real monorepo root is genuinely absent).
        root = _make_repo(tmp_path / "checkout")
        anchor = root / "apps" / "api" / "tests" / "unit" / "test_x.py"
        anchor.parent.mkdir(parents=True)
        anchor.write_text("", encoding="utf-8")
        assert find_repo_root(anchor) == root.resolve()

    def test_is_independent_of_the_current_working_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Same anchor, different CWDs: the result must not change. Uses a
        # constructed tree so the assertion holds in every layout.
        root = _make_repo(tmp_path / "checkout")
        anchor = root / "apps" / "api" / "file.py"
        anchor.parent.mkdir(parents=True, exist_ok=True)
        anchor.write_text("", encoding="utf-8")
        before = find_repo_root(anchor)
        monkeypatch.chdir(tmp_path)
        assert find_repo_root(anchor) == before == root.resolve()

    def test_flat_mount_returns_none_when_not_required(self, tmp_path: Path) -> None:
        # Simulate `/app/tests/unit/test_x.py` with no sentinels anywhere above.
        nested = tmp_path / "app" / "tests" / "unit"
        nested.mkdir(parents=True)
        anchor = nested / "test_x.py"
        anchor.write_text("", encoding="utf-8")
        assert find_repo_root(anchor, required=False) is None

    def test_flat_mount_raises_actionable_error_when_required(self, tmp_path: Path) -> None:
        anchor = tmp_path / "app" / "file.py"
        anchor.parent.mkdir(parents=True)
        anchor.write_text("", encoding="utf-8")
        with pytest.raises(RepoRootNotFound, match=REPO_ROOT_ENV_VAR):
            find_repo_root(anchor, required=True)

    def test_env_override_is_honoured_when_valid(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        fake_root = _make_repo(tmp_path / "fake_repo")
        monkeypatch.setenv(REPO_ROOT_ENV_VAR, str(fake_root))
        # Even anchored at an unrelated location, the override wins.
        assert find_repo_root(tmp_path / "elsewhere" / "x.py") == fake_root.resolve()

    def test_env_override_rejected_when_it_is_not_a_root(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(REPO_ROOT_ENV_VAR, str(tmp_path))  # no sentinels
        with pytest.raises(RepoRootNotFound):
            find_repo_root()

    def test_walks_through_a_symlinked_tree(self, tmp_path: Path) -> None:
        real_root = _make_repo(tmp_path / "real")
        link = tmp_path / "linked"
        try:
            link.symlink_to(real_root, target_is_directory=True)
        except OSError, NotImplementedError:
            pytest.skip("symlink creation not permitted on this platform")
        anchor = link / "apps" / "api" / "deep" / "file.py"
        anchor.parent.mkdir(parents=True, exist_ok=True)
        anchor.write_text("", encoding="utf-8")
        assert find_repo_root(anchor) == real_root.resolve()


class TestFindAppsApiRoot:
    def test_locates_the_apps_api_root(self) -> None:
        root = find_apps_api_root()
        assert (root / "pyproject.toml").exists()
        assert (root / "src" / "main.py").exists()

    def test_apps_api_root_is_this_trees_apps_api(self) -> None:
        # This test file lives under apps/api/tests/unit — the discovered
        # apps/api root must be an ancestor of it.
        here = Path(__file__).resolve()
        assert find_apps_api_root() in here.parents

    def test_raises_when_no_apps_api_root(self, tmp_path: Path) -> None:
        anchor = tmp_path / "nowhere" / "file.py"
        anchor.parent.mkdir(parents=True)
        anchor.write_text("", encoding="utf-8")
        with pytest.raises(RepoRootNotFound):
            find_apps_api_root(anchor)


def test_helper_import_does_not_depend_on_cwd() -> None:
    """The module resolves its own path, so import order/CWD cannot break it."""
    assert "tests._repo_paths" in sys.modules
    # Sanity: os.getcwd is never consulted by find_repo_root.
    assert "getcwd" not in find_repo_root.__code__.co_names
    assert "cwd" not in find_repo_root.__code__.co_names
