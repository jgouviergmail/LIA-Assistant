"""Guard: the lines a change touches are covered at least at the floor (AC-030a).

Why
---
The backend floor is GLOBAL: measured 2026-10-22, the coverage fell 1.7 points in
19 days, from 80.36 % to 78.67 %, a 0.66-point margin where the doctrine asks for
two. New domains landed below the floor (sms 53.6 %, proactive_discussions 70.2 %)
and the global figure absorbed them: nothing measured the code a change adds.

``scripts/audit/diff_coverage.py`` measures exactly that — the lines a change adds
or modifies under ``apps/api/src`` that coverage counts as executable — against
the floor ``apps/api/pyproject.toml`` owns. These tests drive it on a throwaway
git repository built in the test's own temporary directory.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from tests._git_sandbox import isolate_from_the_running_repository, run_git
from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
AUDIT_DIR = REPO_ROOT / "scripts" / "audit"
SCRIPT_PATH = AUDIT_DIR / "diff_coverage.py"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_diff_coverage"


def _load_module() -> ModuleType:
    # The script imports its sibling ``doc_facts`` by name, as it does when run
    # from scripts/audit/: the directory joins the path before it executes.
    if str(AUDIT_DIR) not in sys.path:
        sys.path.insert(0, str(AUDIT_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


diff_coverage = _load_module()

MODULE = "apps/api/src/pkg/mod.py"
BASE_SOURCE = "".join(f"value_{n} = {n}\n" for n in range(1, 11))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    """The script under test runs git itself: never against the repository the tests run in."""
    isolate_from_the_running_repository(monkeypatch)


def _git(root: Path, *args: str) -> str:
    # A throwaway repository: no hook, no signing, whatever the user's config says.
    flags = (
        "-c",
        "core.hooksPath=.no-hooks",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=guard",
        "-c",
        "user.email=guard@example.invalid",
    )
    return run_git(root, *flags, *args).stdout.strip()


def _repo(tmp_path: Path, *, floor: int = 80) -> tuple[Path, str]:
    root = tmp_path / "repo"
    (root / "apps/api/src/pkg").mkdir(parents=True)
    (root / "apps/api/pyproject.toml").write_text(
        f'[tool.pytest.ini_options]\naddopts = "--cov=src --cov-fail-under={floor}"\n',
        encoding="utf-8",
    )
    (root / MODULE).write_text(BASE_SOURCE, encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    return root, _git(root, "rev-parse", "HEAD")


def _coverage(root: Path, files: dict[str, dict[int, int]], *, age_seconds: float = 0) -> None:
    """Write a Cobertura report whose source is the repository's apps/api/src."""
    classes = "".join(
        f'<class name="{name}" filename="{name}"><methods/><lines>'
        + "".join(f'<line number="{n}" hits="{h}"/>' for n, h in sorted(lines.items()))
        + "</lines></class>"
        for name, lines in files.items()
    )
    stamp = int((time.time() + 5 - age_seconds) * 1000)
    (root / "apps/api/coverage.xml").write_text(
        f'<?xml version="1.0" ?><coverage timestamp="{stamp}"><sources>'
        f"<source>{root / 'apps' / 'api' / 'src'}</source></sources><packages>"
        f'<package name="."><classes>{classes}</classes></package></packages></coverage>',
        encoding="utf-8",
    )


def _edit(root: Path, replacements: dict[int, str]) -> None:
    lines = BASE_SOURCE.splitlines(keepends=True)
    for number, text in replacements.items():
        lines[number - 1] = text
    (root / MODULE).write_text("".join(lines), encoding="utf-8")


def _main(root: Path, base: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = diff_coverage.main([str(root), "--base", base])
    return code, capsys.readouterr().out


class TestHunks:
    def test_only_the_added_side_counts(self) -> None:
        diff = (
            "diff --git a/apps/api/src/a.py b/apps/api/src/a.py\n"
            "--- a/apps/api/src/a.py\n+++ b/apps/api/src/a.py\n"
            "@@ -3,0 +4,2 @@\n+x = 1\n+y = 2\n"
            "@@ -9 +11 @@\n-old\n+new\n"
            "@@ -20,2 +22,0 @@\n-gone\n-gone\n"
            "diff --git a/apps/api/src/b.py b/apps/api/src/b.py\n"
            "--- a/apps/api/src/b.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-x\n"
        )
        assert diff_coverage.parse_added_lines(diff) == {"apps/api/src/a.py": {4, 5, 11}}

    def test_line_ranges_read_like_a_reviewer_writes_them(self) -> None:
        assert diff_coverage.ranges([4, 1, 2, 3, 9, 11, 12]) == "1-4, 9, 11-12"


class TestMeasurement:
    def test_an_uncovered_change_below_the_floor_fails_and_names_its_lines(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        _edit(root, {3: "value_3 = 30\n", 4: "value_4 = 40\n", 5: "# a comment line\n"})
        _coverage(root, {"pkg/mod.py": {n: (0 if n == 4 else 1) for n in range(1, 11) if n != 5}})

        code, out = _main(root, base, capsys)

        assert code == 1
        assert "2 changed lines" in out and "50.00 %" in out
        assert f"{MODULE}: 1 of 2 changed lines uncovered: 4" in out

    def test_a_change_covered_at_the_floor_passes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        _edit(root, {3: "value_3 = 30\n", 4: "value_4 = 40\n"})
        _coverage(root, {"pkg/mod.py": dict.fromkeys(range(1, 11), 1)})

        code, out = _main(root, base, capsys)

        assert code == 0 and "100.00 %" in out

    def test_the_floor_is_the_one_pyproject_owns(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path, floor=50)
        _edit(root, {3: "value_3 = 30\n", 4: "value_4 = 40\n"})
        _coverage(root, {"pkg/mod.py": {n: (0 if n == 4 else 1) for n in range(1, 11)}})

        code, out = _main(root, base, capsys)

        assert code == 0 and "floor 50 %" in out

    def test_a_new_untracked_module_counts_as_a_whole(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        (root / "apps/api/src/pkg/new.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
        _coverage(root, {"pkg/mod.py": {1: 1}, "pkg/new.py": {1: 1, 2: 0}})

        code, out = _main(root, base, capsys)

        assert code == 1
        assert "apps/api/src/pkg/new.py: 1 of 2 changed lines uncovered: 2" in out

    def test_a_change_outside_the_measured_tree_measures_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        (root / "apps/api/tests").mkdir(parents=True)
        (root / "apps/api/tests/test_x.py").write_text("def test_x():\n    pass\n")
        (root / "README.md").write_text("# T\n", encoding="utf-8")
        _coverage(root, {"pkg/mod.py": dict.fromkeys(range(1, 11), 1)})

        code, out = _main(root, base, capsys)

        assert code == 0 and "no measured line changed" in out

    def test_a_moved_module_without_edits_measures_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, base = _repo(tmp_path)
        # Whatever the user's configuration says about renames.
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "diff.renames")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "false")
        _git(root, "mv", MODULE, "apps/api/src/pkg/moved.py")
        _coverage(root, {"pkg/moved.py": dict.fromkeys(range(1, 11), 0)})

        code, out = _main(root, base, capsys)

        assert code == 0 and "no measured line changed" in out

    def test_a_report_older_than_the_change_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        _coverage(root, {"pkg/mod.py": dict.fromkeys(range(1, 11), 1)}, age_seconds=3600)
        _edit(root, {3: "value_3 = 30\n"})

        code, out = _main(root, base, capsys)

        assert code == 1 and "older than the change" in out

    def test_a_report_of_another_tree_is_refused(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)
        _edit(root, {3: "value_3 = 30\n"})
        _coverage(root, {"pkg/mod.py": dict.fromkeys(range(1, 11), 1)})
        report = root / "apps/api/coverage.xml"
        report.write_text(
            report.read_text(encoding="utf-8").replace("src</source>", "lib</source>"),
            encoding="utf-8",
        )

        code, out = _main(root, base, capsys)

        assert code == 1 and "does not measure apps/api/src" in out

    def test_a_missing_report_says_which_task_writes_it(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, base = _repo(tmp_path)

        code, out = _main(root, base, capsys)

        assert code == 1 and "task test:backend:coverage" in out


class TestBase:
    def test_an_empty_ci_base_skips_with_a_notice(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, _base = _repo(tmp_path)
        monkeypatch.setenv("DIFF_COVERAGE_BASE", "")
        assert diff_coverage.main([str(root)]) == 0
        assert "no base" in capsys.readouterr().out

    def test_the_zero_sha_of_a_new_branch_is_no_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, _base = _repo(tmp_path)
        monkeypatch.setenv("DIFF_COVERAGE_BASE", "0" * 40)
        assert diff_coverage.resolve_base(root, None) is None

    def test_the_ci_base_comes_from_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, base = _repo(tmp_path)
        monkeypatch.setenv("DIFF_COVERAGE_BASE", base)
        assert diff_coverage.resolve_base(root, None) == base

    def test_locally_the_base_is_where_the_branch_left_main(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root, base = _repo(tmp_path)
        monkeypatch.delenv("DIFF_COVERAGE_BASE", raising=False)
        _git(root, "checkout", "-q", "-b", "topic")
        (root / "apps/api/src/pkg/other.py").write_text("x = 1\n", encoding="utf-8")
        _git(root, "add", "-A")
        _git(root, "commit", "-q", "-m", "topic")
        assert diff_coverage.resolve_base(root, None) == base

    def test_a_shallow_checkout_fetches_its_base_alone(self, tmp_path: Path) -> None:
        """The CI path: actions/checkout holds HEAD only; the base is fetched on demand."""
        origin, base = _repo(tmp_path)
        _git(origin, "config", "uploadpack.allowReachableSHA1InWant", "true")
        _edit(origin, {3: "value_3 = 30\n"})
        _git(origin, "commit", "-q", "-am", "head")
        clone = tmp_path / "clone"
        _git(tmp_path, "clone", "-q", "--depth=1", origin.as_uri(), str(clone))
        assert diff_coverage._commit(clone, base) is None

        assert diff_coverage.resolve_base(clone, base) == base

    def test_an_unknown_base_is_an_error_not_a_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root, _base = _repo(tmp_path)
        _coverage(root, {"pkg/mod.py": {1: 1}})

        code, out = _main(root, "f" * 40, capsys)

        assert code == 1 and "base" in out


def test_the_ci_job_runs_the_gate_after_the_coverage_it_reads() -> None:
    """ADR-151: the workflow calls the task; the base travels in the environment.

    The gate reads what BOTH suites cover (AC-030b): it runs in the job that
    combines them, after the combination.
    """
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    (steps,) = [
        job["steps"]
        for job in workflow["jobs"].values()
        if any(step.get("run") == "task test:backend:diff-coverage" for step in job["steps"])
    ]
    runs = [step.get("run") for step in steps]
    gate = runs.index("task test:backend:diff-coverage")
    assert runs.index("task test:backend:coverage") < gate
    assert "DIFF_COVERAGE_BASE" in steps[gate]["env"]


def _subtasks(name: str) -> list[str]:
    tasks = yaml.safe_load((REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8"))["tasks"]
    return [entry["task"] for entry in tasks[name]["cmds"] if isinstance(entry, dict)]


def test_the_local_ci_runs_the_gate_after_the_coverage_it_reads() -> None:
    full = _subtasks("ci")
    assert "ci:fast" in full and "test:backend:unit:coverage" in _subtasks("ci:fast")
    assert (
        full.index("ci:fast")
        < full.index("test:backend:integration")
        < full.index("test:backend:coverage")
        < full.index("test:backend:diff-coverage")
    )


def test_the_service_free_ci_holds_no_gate_it_cannot_measure() -> None:
    """Without the integration suite, a floor or a diff gate would read half the total."""
    fast = _subtasks("ci:fast")
    assert "test:backend:coverage" not in fast and "test:backend:diff-coverage" not in fast
