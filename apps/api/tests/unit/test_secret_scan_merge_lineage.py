"""The production scan must see incoming branches and a merge's own resolution."""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _commit(repo: Path, value: str) -> str:
    (repo / "shared.txt").write_text(value + "\n", encoding="utf-8")
    _git(repo, "add", "shared.txt")
    _git(repo, "commit", "-m", "lineage proof")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def merged_repo(tmp_path: Path) -> tuple[Path, str, set[str]]:
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "Lineage proof")
    _git(tmp_path, "config", "user.email", "proof@local.invalid")
    _git(tmp_path, "config", "core.hooksPath", ".git/hooks")
    start = _commit(tmp_path, "base")
    _git(tmp_path, "switch", "-c", "feature")
    feature = _commit(tmp_path, "feature branch value")
    _git(tmp_path, "switch", "main")
    main = _commit(tmp_path, "main branch value")
    conflict = subprocess.run(
        ["git", "merge", "--no-ff", "feature", "-m", "merge proof"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert conflict.returncode == 1, "the fixture must exercise a real merge resolution"
    merge = _commit(tmp_path, "value created only in the merge resolution")
    return tmp_path, start, {feature, main, merge}


def _production_log_options(start: str) -> list[str]:
    taskfile = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    command = taskfile["tasks"]["security:secrets"]["cmds"][0]["cmd"]
    options = re.search(r'--log-opts="([^"]+)"', command)
    assert options is not None, "the production scanner must declare its Git history scope"
    return shlex.split(options.group(1).replace("{{.RANGE}}", f"{start}..HEAD"))


def test_every_incoming_commit_is_scanned(merged_repo: tuple[Path, str, set[str]]) -> None:
    repo, start, expected = merged_repo
    output = _git(repo, "log", "--format=COMMIT:%H", *_production_log_options(start))
    commits = {
        line.removeprefix("COMMIT:") for line in output.splitlines() if line.startswith("COMMIT:")
    }
    assert commits == expected, "the scan omitted an incoming branch or its merge"


def test_the_merge_resolution_is_visible_to_the_scanner(
    merged_repo: tuple[Path, str, set[str]],
) -> None:
    repo, start, _ = merged_repo
    patch = _git(repo, "log", "-p", "--format=%H", *_production_log_options(start))
    assert "+value created only in the merge resolution" in patch
