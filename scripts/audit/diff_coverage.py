#!/usr/bin/env python3
"""Diff coverage: the lines a change touches are covered at least at the floor (AC-030a).

Why
---
The backend coverage floor is GLOBAL, so new code could land below it unseen while
the total still passed: measured 2026-10-22, the coverage fell 1.7 points in 19
days (80.36 % to 78.67 %), and new domains sat far under the floor (sms 53.6 %,
proactive_discussions 70.2 %). Nothing measured the code a change adds.

Contract
--------
The lines a change ADDS or MODIFIES under ``apps/api/src`` — compared with a base
commit, uncommitted edits and new untracked modules included — that coverage
counts as executable must be covered at least at the floor ``apps/api/pyproject.toml``
owns (``--cov-fail-under``, read through ``doc_facts.floor_values``: one source).
The report is the ``apps/api/coverage.xml`` that ``task test:backend:coverage``
writes over the unit and integration suites together (AC-030b): a line either suite
executes is covered. A report older than the change is refused, because its line
numbers no longer describe the code.

Base
----
``--base``, else ``DIFF_COVERAGE_BASE`` (set by CI: the pull request's base, or the
commit a push started from), else where the branch left ``origin/main`` (or
``main``). In CI an EMPTY variable, or the zero SHA of a new branch, means there is
nothing to compare with: the gate says so and passes. A base the shallow CI
checkout lacks is fetched alone (``--depth=1``). Renames are followed, so a moved
module counts only the lines its move changed — once the move is staged: an
untracked file is new as a whole.

Usage (from any working directory):
    python scripts/audit/diff_coverage.py [REPO_ROOT] [--base REF] [--coverage PATH]

Standard library only. Imports its sibling ``doc_facts`` by name: run from
``scripts/audit/`` as a script, Python puts that directory first on the path.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from doc_facts import floor_values

__all__ = [
    "BASE_ENV",
    "MEASURED_TREE",
    "FileResult",
    "Report",
    "changed_lines",
    "load_report",
    "main",
    "measure",
    "parse_added_lines",
    "ranges",
    "resolve_base",
]

#: The tree the backend coverage measures (``--cov=src`` from ``apps/api``).
MEASURED_TREE = "apps/api/src"
#: Where CI hands the base commit over (ADR-151: the workflow sets, the task reads).
BASE_ENV = "DIFF_COVERAGE_BASE"
_REPORT_REL = "apps/api/coverage.xml"
_PYPROJECT_REL = "apps/api/pyproject.toml"
_COVERAGE_TASK = "task test:backend:coverage"
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")
_ZERO_SHA = re.compile(r"^0+$")
#: Clock slack between a file's mtime and the report's own timestamp.
_STALENESS_SLACK_SECONDS = 1.0


class DiffCoverageError(RuntimeError):
    """The gate cannot reach a verdict: missing report or base, stale report."""


@dataclass(frozen=True)
class Report:
    """A Cobertura report: when it was written, and the hits of every measured line."""

    timestamp: float
    hits: dict[str, dict[int, int]]


@dataclass(frozen=True)
class FileResult:
    """The changed executable lines of one file, and those no test ran."""

    path: str
    measured: tuple[int, ...]
    uncovered: tuple[int, ...]


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise DiffCoverageError(f"git {' '.join(args)}: {completed.stderr.strip()}")
    return completed.stdout


def _commit(root: Path, ref: str) -> str | None:
    try:
        return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").strip()
    except DiffCoverageError:
        return None


def resolve_base(root: Path, explicit: str | None) -> str | None:
    """The commit to compare with, or None when there is none to compare with.

    Args:
        root: Repository root.
        explicit: ``--base``, when given.

    Returns:
        The base commit's SHA, or None (an empty CI base, or a new branch's zero SHA).

    Raises:
        DiffCoverageError: If the base names a commit nobody can find.
    """
    if explicit is not None:
        candidate = explicit.strip()
    elif (from_env := os.environ.get(BASE_ENV)) is not None:
        candidate = from_env.strip()
    else:
        for upstream in ("origin/main", "main"):
            try:
                return _git(root, "merge-base", "HEAD", upstream).strip()
            except DiffCoverageError:
                continue
        raise DiffCoverageError("no base: neither origin/main nor main is reachable; pass --base")
    if not candidate or _ZERO_SHA.match(candidate):
        return None
    found = _commit(root, candidate)
    if found is None:
        # A shallow CI checkout holds HEAD alone: fetch the base, and the base only.
        try:
            _git(root, "fetch", "--no-tags", "--quiet", "--depth=1", "origin", candidate)
        except DiffCoverageError:
            pass
        found = _commit(root, candidate)
    if found is None:
        raise DiffCoverageError(f"cannot find the base commit {candidate}")
    return found


def parse_added_lines(diff: str) -> dict[str, set[int]]:
    """The added line numbers of every file a ``--unified=0`` diff touches.

    Args:
        diff: ``git diff --unified=0`` output.

    Returns:
        ``{repository path: added line numbers}``; deleted files are absent.
    """
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        match = _HUNK.match(line)
        if match is None or current is None:
            continue
        start, count = int(match["start"]), int(match["count"] or "1")
        if count:
            added.setdefault(current, set()).update(range(start, start + count))
    return added


def changed_lines(root: Path, base: str) -> dict[str, set[int]]:
    """The lines a change adds or modifies in the measured tree's Python modules.

    Args:
        root: Repository root.
        base: The base commit.

    Returns:
        ``{repository path: line numbers}`` for every touched ``.py`` file.
    """
    diff = _git(
        root,
        "diff",
        "--unified=0",
        "--no-color",
        "--no-ext-diff",
        "--find-renames",
        "--diff-filter=AMR",
        base,
        "--",
        MEASURED_TREE,
    )
    changed = parse_added_lines(diff)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", "--", MEASURED_TREE)
    for rel in filter(None, untracked.split("\0")):
        text = (root / rel).read_text(encoding="utf-8", errors="replace")
        changed[rel] = set(range(1, text.count("\n") + 2))
    return {rel: lines for rel, lines in changed.items() if rel.endswith(".py")}


def load_report(path: Path) -> Report:
    """Read a Cobertura report written for the measured tree.

    Args:
        path: The ``coverage.xml`` file.

    Returns:
        The report, keyed by repository path.

    Raises:
        DiffCoverageError: If the report does not measure ``apps/api/src``.
    """
    tree = ElementTree.parse(path).getroot()
    sources = [(source.text or "").replace("\\", "/").rstrip("/") for source in tree.iter("source")]
    if not any(source.endswith(MEASURED_TREE) for source in sources):
        raise DiffCoverageError(f"{path} does not measure {MEASURED_TREE}")
    stamp = tree.get("timestamp")
    timestamp = int(stamp) / 1000 if stamp and stamp.isdigit() else path.stat().st_mtime
    hits: dict[str, dict[int, int]] = {}
    for element in tree.iter("class"):
        rel = f"{MEASURED_TREE}/{element.get('filename', '')}"
        lines = hits.setdefault(rel, {})
        for line in element.iter("line"):
            lines[int(line.get("number", "0"))] = int(line.get("hits", "0"))
    return Report(timestamp, hits)


def measure(changed: dict[str, set[int]], report: Report) -> list[FileResult]:
    """Intersect the changed lines with the lines coverage counts as executable.

    Args:
        changed: The changed lines, by repository path.
        report: The coverage report.

    Returns:
        One result per file that has at least one changed executable line.
    """
    results = []
    for rel in sorted(changed):
        executable = report.hits.get(rel, {})
        measured = sorted(line for line in changed[rel] if line in executable)
        if measured:
            uncovered = tuple(line for line in measured if executable[line] == 0)
            results.append(FileResult(rel, tuple(measured), uncovered))
    return results


def ranges(lines: Iterable[int]) -> str:
    """Compress line numbers into reviewer-style ranges (``1-4, 9, 11-12``)."""
    ordered = sorted(set(lines))
    spans: list[str] = []
    start = previous = ordered[0] if ordered else 0
    for line in ordered[1:] + [None]:
        if line is not None and line == previous + 1:
            previous = line
            continue
        spans.append(str(start) if start == previous else f"{start}-{previous}")
        if line is not None:
            start = previous = line
    return ", ".join(spans) if ordered else ""


def _floor(root: Path) -> str:
    values = floor_values((root / _PYPROJECT_REL).read_text(encoding="utf-8"))
    if len(values) != 1:
        raise DiffCoverageError(f"{_PYPROJECT_REL} must state one coverage floor, found {values}")
    return values.pop()


def _verdict(root: Path, base: str, report_path: Path) -> int:
    if not report_path.is_file():
        raise DiffCoverageError(f"{_REPORT_REL} is missing; run {_COVERAGE_TASK} first")
    report = load_report(report_path)
    changed = changed_lines(root, base)
    for rel in changed:
        if (root / rel).stat().st_mtime > report.timestamp + _STALENESS_SLACK_SECONDS:
            raise DiffCoverageError(
                f"{_REPORT_REL} is older than the change ({rel}); run {_COVERAGE_TASK} again"
            )
    results = measure(changed, report)
    if not results:
        print(f"diff_coverage: no measured line changed since {base[:12]}")
        return 0
    floor = _floor(root)
    total = sum(len(result.measured) for result in results)
    covered = total - sum(len(result.uncovered) for result in results)
    ratio = 100 * covered / total
    print(
        f"diff_coverage: {total} changed lines measured in {len(results)} files, "
        f"{covered} covered ({ratio:.2f} %), floor {floor} %"
    )
    for result in results:
        if result.uncovered:
            print(
                f"diff_coverage: {result.path}: {len(result.uncovered)} of "
                f"{len(result.measured)} changed lines uncovered: {ranges(result.uncovered)}"
            )
    if ratio < float(floor):
        print(f"diff_coverage: error: the change is covered below the floor ({floor} %)")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Measure the change's coverage against the floor.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        0 when the change is covered at the floor or there is nothing to measure,
        1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--base", default=None, help="the commit to compare with")
    parser.add_argument("--coverage", type=Path, default=None, help=f"default: {_REPORT_REL}")
    args = parser.parse_args(argv)
    root: Path = args.root
    try:
        base = resolve_base(root, args.base)
        if base is None:
            print(
                f"diff_coverage: no base to compare with ({BASE_ENV} is empty): nothing to measure"
            )
            return 0
        return _verdict(root, base, args.coverage or root / _REPORT_REL)
    except (DiffCoverageError, OSError, ElementTree.ParseError) as exc:
        print(f"diff_coverage: error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
