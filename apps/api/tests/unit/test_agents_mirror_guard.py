"""Guard: AGENTS.md is a generated mirror of CLAUDE.md, never a second copy.

Why
---
Both files tell a coding agent how to work here; only the tool that reads them
differs. Maintained by hand they drifted, and the drift was not cosmetic.
Measured 2026-08-27:

* ``AGENTS.md`` carried 22 sections against ``CLAUDE.md``'s 40, a **strict
  subset** with nothing of its own;
* the 18 absent sections were the whole of "Systemic Rules (hard-won)" and
  "Audit-Derived Quality Gates" — the JSONB-mutation rule, the ``AsyncSession``
  concurrency rule, timezone-aware UTC, the ``zh-CN`` backend canonical, the
  file-size ratchet, the empty-``except`` ban;
* it also stated a 43 % coverage floor against a real 67 %.

A stale instruction file is worse than a missing one: an agent obeys it, and
here it would have obeyed rules the repository fails builds over. Generating the
mirror removes the possibility rather than the symptom — same doctrine as
``version_surfaces.py`` for release surfaces.

The ``TestMirrorSanity`` class guards the generator itself: a renderer that
produced an empty body would make "mirror matches" true and vacuous, which is
the failure mode found in the neighbouring coverage-threshold guard.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._git_sandbox import (
    isolate_from_the_running_repository,
    isolated_git_env,
    run_git,
)
from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
MIRROR_PATH = REPO_ROOT / "scripts" / "audit" / "agents_mirror.py"
HOOK_PATH = REPO_ROOT / ".github" / "hooks" / "pre-commit"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_agents_mirror"

#: Anti-rot floor. CLAUDE.md carried 40 '## '/'### ' sections on 2026-08-27; a
#: render that suddenly mirrors a handful is broken, not tidy.
MIN_EXPECTED_SECTIONS = 25


def _load() -> ModuleType:
    """Load the mirror module shared with the linter and the sync task."""
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    if not MIRROR_PATH.is_file():
        pytest.skip("guard needs the full repository checkout (scripts/audit/agents_mirror.py).")
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, MIRROR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception:  # pragma: no cover - a failed import must not leave a stub
        del sys.modules[_MODULE_NAME]
        raise
    return module


_mirror = _load()


def _sections(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith(("## ", "### "))]


class TestMirrorSanity:
    """Guard the generator: an empty render would match trivially."""

    def test_the_source_exists_and_has_a_body(self) -> None:
        try:
            rendered = _mirror.render_mirror(REPO_ROOT)
        except _mirror.MirrorError as error:  # pragma: no cover - failure path
            pytest.fail(str(error))

        assert len(_sections(rendered)) >= MIN_EXPECTED_SECTIONS, (
            f"the render carries only {len(_sections(rendered))} sections "
            f"(expected at least {MIN_EXPECTED_SECTIONS}). An almost-empty mirror "
            "would satisfy the equality test while telling an agent nothing."
        )

    def test_the_render_is_deterministic(self) -> None:
        """Two renders must be byte-identical, or CI and the fixer disagree."""
        assert _mirror.render_mirror(REPO_ROOT) == _mirror.render_mirror(REPO_ROOT)

    def test_the_render_declares_itself_generated(self) -> None:
        """A reader who opens the mirror first must be sent to the source."""
        rendered = _mirror.render_mirror(REPO_ROOT)

        assert "GENERATED FILE" in rendered and _mirror.SOURCE in rendered

    def test_both_files_stay_at_the_repository_root(self) -> None:
        """The verbatim copy is only correct while both share one link base.

        ``CLAUDE.md`` is full of relative links and code paths. They resolve in
        ``AGENTS.md`` because both files sit at the root — move either into a
        subdirectory and every one of them breaks in the mirror, silently, with
        no gate able to tell (the copy would still match its render).
        """
        for name in (_mirror.SOURCE, _mirror.MIRROR):
            assert "/" not in name and "\\" not in name, (
                f"{name!r} is no longer a root-level filename. The mirror copies "
                "the body verbatim; relative links only survive that copy while "
                "source and mirror share a directory."
            )
            assert (REPO_ROOT / name).is_file(), f"{name} is missing from the root"

    def test_a_source_opening_on_a_section_is_mirrored_whole(self, tmp_path: Path) -> None:
        """Edge case: a document whose very first line is a '## ' heading."""
        (tmp_path / _mirror.SOURCE).write_text("## Only\n\nbody\n", encoding="utf-8")

        assert "## Only" in _mirror.render_mirror(tmp_path)

    def test_a_source_without_any_section_fails_loudly(self, tmp_path: Path) -> None:
        """An empty body would make 'the mirror matches' true and meaningless."""
        (tmp_path / _mirror.SOURCE).write_text("# Title only\n", encoding="utf-8")

        with pytest.raises(_mirror.MirrorError):
            _mirror.render_mirror(tmp_path)


class TestSystemicRulesSurvive:
    """The sections whose absence caused this guard must be in the mirror."""

    @pytest.mark.parametrize(
        "heading",
        [
            "## Systemic Rules (hard-won)",
            "## Audit-Derived Quality Gates (Security Excluded)",
            "### Concurrency & async",
            "### Persistence",
            "### Registries & vocabulary",
            "### i18n & prompts",
            "### Observability & honesty",
            "### Size & structure",
        ],
    )
    def test_heading_is_mirrored(self, heading: str) -> None:
        assert heading in _mirror.render_mirror(REPO_ROOT), (
            f"{heading!r} is absent from the generated AGENTS.md. This exact "
            "class of omission is why the file is generated."
        )


class TestRepository:
    """The real assertion: the file on disk is the current render."""

    def test_agents_md_is_in_sync(self) -> None:
        assert _mirror.mirror_is_current(REPO_ROOT), (
            "AGENTS.md has drifted from CLAUDE.md. It is a GENERATED mirror — "
            "edit CLAUDE.md, then run `task docs:sync-agents`."
        )

    def test_the_two_files_agree_section_for_section(self) -> None:
        """Beyond byte equality, state the failure in the terms that matter."""
        claude = _sections((REPO_ROOT / _mirror.SOURCE).read_text(encoding="utf-8"))
        agents = _sections((REPO_ROOT / _mirror.MIRROR).read_text(encoding="utf-8"))
        missing = [section for section in claude if section not in agents]

        assert not missing, (
            f"{len(missing)} section(s) of CLAUDE.md are absent from AGENTS.md, "
            f"starting with {missing[0]!r}. Run `task docs:sync-agents`."
        )


_SOURCE_TEXT = "# Title\n\n## Rules\n\nbody\n"


def _write(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8", newline="\n")


def _new_rule(root: Path) -> None:
    """Change the source in the working copy, the way a session adds a rule."""
    _write(root, _mirror.SOURCE, _SOURCE_TEXT + "\nanother rule\n")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway repository whose index holds an agreeing pair."""
    isolate_from_the_running_repository(monkeypatch)
    run_git(tmp_path, "init", "-q")
    _write(tmp_path, _mirror.SOURCE, _SOURCE_TEXT)
    _mirror.write_mirror(tmp_path)
    run_git(tmp_path, "add", _mirror.SOURCE, _mirror.MIRROR)
    return tmp_path


class TestStagedPair:
    """The pair a commit carries is judged, never the working copy."""

    def test_an_agreeing_pair_passes(self, repo: Path) -> None:
        assert _mirror.staged_mirror_is_current(repo)

    def test_a_source_staged_without_its_mirror_fails(self, repo: Path) -> None:
        _new_rule(repo)
        run_git(repo, "add", _mirror.SOURCE)

        assert not _mirror.staged_mirror_is_current(repo)

    def test_a_mirror_regenerated_but_not_staged_fails(self, repo: Path) -> None:
        """The working copy is in sync; what the commit would carry is not."""
        _new_rule(repo)
        run_git(repo, "add", _mirror.SOURCE)
        _mirror.write_mirror(repo)

        assert _mirror.mirror_is_current(repo)
        assert not _mirror.staged_mirror_is_current(repo)

    def test_a_mirror_edited_by_hand_fails(self, repo: Path) -> None:
        _write(repo, _mirror.MIRROR, _mirror.render_mirror(repo) + "\nedited by an agent\n")
        run_git(repo, "add", _mirror.MIRROR)

        assert not _mirror.staged_mirror_is_current(repo)

    def test_an_unstaged_edit_does_not_count(self, repo: Path) -> None:
        _new_rule(repo)

        assert _mirror.staged_mirror_is_current(repo)

    def test_the_commit_index_named_by_git_is_the_one_read(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`git commit -a` builds the commit from a temporary index."""
        temporary = repo / "commit-index"
        shutil.copy(repo / ".git" / "index", temporary)
        _new_rule(repo)
        run_git(repo, "add", _mirror.SOURCE, env={"GIT_INDEX_FILE": str(temporary)})
        run_git(repo, "reset", "-q")
        run_git(repo, "add", _mirror.SOURCE, _mirror.MIRROR)
        monkeypatch.setenv("GIT_INDEX_FILE", str(temporary))

        assert not _mirror.staged_mirror_is_current(repo)

    def test_a_file_missing_from_the_index_is_an_error(self, repo: Path) -> None:
        run_git(repo, "rm", "-q", "--cached", _mirror.MIRROR)

        with pytest.raises(_mirror.MirrorError):
            _mirror.staged_mirror_is_current(repo)

    def test_it_never_writes(self, repo: Path) -> None:
        """A regeneration would erase an edit an agent made to the mirror."""
        edited = _mirror.render_mirror(repo) + "\nedited by an agent\n"
        _write(repo, _mirror.MIRROR, edited)
        run_git(repo, "add", _mirror.MIRROR)

        assert _mirror.main(["mirror", str(repo), "--staged"]) == 1
        assert (repo / _mirror.MIRROR).read_text(encoding="utf-8") == edited

    def test_the_refusal_names_both_repairs(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _new_rule(repo)
        run_git(repo, "add", _mirror.SOURCE)

        assert _mirror.main(["mirror", str(repo), "--staged"]) == 1

        message = capsys.readouterr().err
        assert "task docs:sync-agents" in message
        assert "edited by hand" in message

    def test_a_missing_file_exits_two(self, repo: Path) -> None:
        run_git(repo, "rm", "-q", "--cached", _mirror.SOURCE)

        assert _mirror.main(["mirror", str(repo), "--staged"]) == 2


class TestThePreCommitHook:
    """The real hook, end to end: a commit with no Python file used to skip the check."""

    @pytest.fixture
    def hooked(self, repo: Path) -> Path:
        hooks = repo / ".github" / "hooks"
        hooks.mkdir(parents=True)
        shutil.copy(HOOK_PATH, hooks / "pre-commit")
        (hooks / "pre-commit").chmod(0o755)
        audit = repo / "scripts" / "audit"
        audit.mkdir(parents=True)
        shutil.copy(MIRROR_PATH, audit / "agents_mirror.py")
        _write(repo, "notes.md", "a note\n")
        run_git(repo, "add", ".")
        self._commit(repo, "--no-verify", "-m", "baseline")
        run_git(repo, "config", "core.hooksPath", ".github/hooks")
        return repo

    @staticmethod
    def _commit(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        env = isolated_git_env(
            {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
        )
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.test", "commit", *args],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_a_source_committed_alone_is_refused(self, hooked: Path) -> None:
        _new_rule(hooked)
        run_git(hooked, "add", _mirror.SOURCE)

        result = self._commit(hooked, "-m", "rule")

        assert result.returncode == 1, result.stdout + result.stderr
        assert "task docs:sync-agents" in result.stdout + result.stderr

    def test_a_synchronised_pair_is_committed(self, hooked: Path) -> None:
        _new_rule(hooked)
        _mirror.write_mirror(hooked)
        run_git(hooked, "add", _mirror.SOURCE, _mirror.MIRROR)

        result = self._commit(hooked, "-m", "rule")

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_mirror_regenerated_but_not_staged_is_refused(self, hooked: Path) -> None:
        _new_rule(hooked)
        run_git(hooked, "add", _mirror.SOURCE)
        _mirror.write_mirror(hooked)

        result = self._commit(hooked, "-m", "rule")

        assert result.returncode == 1, result.stdout + result.stderr

    def test_commit_all_is_judged_on_its_own_index(self, hooked: Path) -> None:
        """`git commit -a`: nothing staged beforehand, the check must still see the file."""
        _new_rule(hooked)

        result = self._commit(hooked, "-a", "-m", "rule")

        assert result.returncode == 1, result.stdout + result.stderr

    def test_commit_all_of_a_synchronised_pair_is_committed(self, hooked: Path) -> None:
        _new_rule(hooked)
        _mirror.write_mirror(hooked)

        result = self._commit(hooked, "-a", "-m", "rule")

        assert result.returncode == 0, result.stdout + result.stderr

    def test_a_commit_touching_neither_file_skips_the_check(self, hooked: Path) -> None:
        _write(hooked, "notes.md", "another note\n")
        run_git(hooked, "add", "notes.md")

        result = self._commit(hooked, "-m", "note")

        assert result.returncode == 0, result.stdout + result.stderr
        assert "skipping mirror check" in result.stdout + result.stderr


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
