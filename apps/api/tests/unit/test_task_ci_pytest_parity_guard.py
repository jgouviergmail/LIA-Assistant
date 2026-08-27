"""Task and CI must select the SAME pytest sets AND agree on coverage policy (F022).

The unit / agents / integration test commands live in BOTH ``Taskfile.yml`` and
``.github/workflows/ci.yml``. If their ``-m`` marker expressions drift, a green
``task test:backend:*`` locally can hide tests that CI runs (or vice-versa) — the
exact "multiple contracts" the audit flagged. This guard extracts the marker
expression each file uses for each test root and asserts they are identical
(order-independent), and that the two commands within a file (Windows/Unix
variants, or a job + its collection step) agree with each other.

It also separates **functional selection** (markers, which MUST match) from the
**coverage threshold** (which is deliberately asymmetric — partial subsets never
enforce the global gate) and pins the threshold to a single source of truth so the
``--cov-fail-under`` number cannot silently diverge between ``pyproject.toml`` and CI.

Finally it forbids a task from running the **same collection twice**. The marker
comparison above works on SETS of expressions, so two identical invocations
collapse into one entry and are invisible to it — which is exactly how a
duplicated F006 collection shipped on 2026-07-25 and doubled that pass both
locally and in CI (the workflow calls the task).
"""

from __future__ import annotations

import re

import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
TASKFILE = REPO_ROOT / "Taskfile.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PRE_COMMIT_HOOK = REPO_ROOT / ".github" / "hooks" / "pre-commit"
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"

_TEST_ROOTS = ("unit", "agents", "integration")
# How a pytest invocation starts in each of the three files: the literal binary
# in Taskfile.yml/ci.yml, and the cross-platform ``$PYTEST_BIN`` the hook
# resolves to ``.venv/Scripts/pytest`` or ``.venv/bin/pytest``.
_RUNNER = r"(?:pytest|\$PYTEST_BIN)"
# ``pytest tests/<root>/ ... -m "<expr>"`` — CI splits the command across
# backslash-continued lines, so continuations are joined first.
_PYTEST_M = re.compile(_RUNNER + r'\s+tests/(unit|agents|integration)/[^\n]*?-m\s+"([^"]+)"')
# The full flag tail of every ``pytest tests/<root>/`` command (post line-join).
_PYTEST_CMD = re.compile(_RUNNER + r"\s+tests/(unit|agents|integration)/([^\n]*)")
_COV_FAIL_UNDER = re.compile(r"--cov-fail-under=(\d+)")


def _markers_by_root(text: str) -> dict[str, set[frozenset[str]]]:
    """Map each test root to the SET of distinct marker expressions found for it."""
    joined = text.replace("\\\n", " ")
    found: dict[str, set[frozenset[str]]] = {}
    for match in _PYTEST_M.finditer(joined):
        root = match.group(1)
        terms = frozenset(t.strip() for t in match.group(2).split(" and "))
        found.setdefault(root, set()).add(terms)
    return found


def _pytest_commands(text: str) -> list[tuple[str, str]]:
    """Return ``(root, flag_tail)`` for every ``pytest tests/<root>/`` command."""
    joined = text.replace("\\\n", " ")
    return [(m.group(1), m.group(2)) for m in _PYTEST_CMD.finditer(joined)]


def test_task_and_ci_are_present() -> None:
    assert TASKFILE.is_file() and CI_WORKFLOW.is_file()


def _is_integration_only(expr: frozenset[str]) -> bool:
    """True for the F006 second pass that selects ONLY integration-marked tests."""
    return "integration" in expr and "not integration" not in expr


def test_each_file_is_internally_consistent_per_root() -> None:
    """A root runs in at most two complementary passes: a main pass (excludes
    integration) and the F006 integration pass (selects only integration). Two
    conflicting *main* passes — or two integration passes — for one root are a
    real inconsistency (F022)."""
    for name, path in (("Taskfile.yml", TASKFILE), ("ci.yml", CI_WORKFLOW)):
        by_root = _markers_by_root(path.read_text(encoding="utf-8"))
        for root, exprs in by_root.items():
            integ = {e for e in exprs if _is_integration_only(e)}
            main = exprs - integ
            assert len(main) <= 1 and len(integ) <= 1, (
                f"{name}: tests/{root}/ is run with divergent -m expressions "
                f"(F022): {[sorted(e) for e in exprs]}"
            )


# Jobs allowed to spell out their own pytest command. Each needs a reason: it is
# the list of places where CI does NOT run what a developer can run.
_PYTEST_ALLOWED_CI_JOBS = {
    "python-compat": (
        "F041 forward-compatibility run on Python 3.13. Its whole point is a "
        "different interpreter from the one every task uses, so it cannot be a "
        "task call. Declared CI-only in scripts/audit/check_ci_parity.py."
    ),
}


def test_ci_does_not_define_its_own_pytest_contract() -> None:
    """CI must CALL the Taskfile suites, not restate them.

    This replaces the original marker-drift comparison, and for a better reason
    than the comparison itself: since ci.yml invokes `task test:backend:*`, the
    two cannot drift — there is only one contract left to drift from. What has
    to be protected now is that property, so the guard fails when a pytest
    command reappears in the workflow and quietly recreates the second contract.

    The marker expressions themselves stay covered by
    `test_each_file_is_internally_consistent_per_root` on the Taskfile side.
    """
    workflow = yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))

    offenders: list[str] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        if job_name in _PYTEST_ALLOWED_CI_JOBS:
            continue
        for step in job.get("steps") or []:
            command = step.get("run", "")
            if re.search(r"pytest\s+tests/(unit|agents|integration)/", command):
                offenders.append(f"{job_name} / {step.get('name', '<unnamed>')}")

    assert not offenders, (
        "these CI steps spell out a pytest command instead of calling a task, "
        f"recreating the drift F022 exists to prevent: {offenders}. "
        "Call `task test:backend:...`, or add the job to _PYTEST_ALLOWED_CI_JOBS "
        "with a written reason."
    )


def test_every_test_root_is_still_driven_by_a_task() -> None:
    """The Taskfile remains the place where the suites are actually defined.

    Counterpart to the test above: proving CI does not restate the commands is
    worthless if the commands stopped existing anywhere.
    """
    task = _markers_by_root(TASKFILE.read_text(encoding="utf-8"))
    for root in _TEST_ROOTS:
        assert root in task, f"tests/{root}/ pytest command missing from Taskfile.yml"


def test_partial_subsets_never_enforce_the_global_coverage_gate() -> None:
    """agents + integration commands run a partial subset, so they must use
    ``--no-cov`` and never carry ``--cov-fail-under`` — otherwise the command exits
    1 despite all tests passing (the trap the Taskfile comment warns about; F022).
    Functional selection is separated from the coverage threshold here."""
    for name, path in (("Taskfile.yml", TASKFILE), ("ci.yml", CI_WORKFLOW)):
        for root, tail in _pytest_commands(path.read_text(encoding="utf-8")):
            if root in ("agents", "integration"):
                assert "--no-cov" in tail, (
                    f"{name}: tests/{root}/ command must pass --no-cov (partial subset, "
                    f"F022): pytest tests/{root}/{tail.strip()}"
                )
                assert "--cov-fail-under" not in tail, (
                    f"{name}: tests/{root}/ must NOT enforce --cov-fail-under on a partial "
                    f"subset (F022): pytest tests/{root}/{tail.strip()}"
                )


def test_the_hook_selects_exactly_what_the_fast_task_selects() -> None:
    """The pre-commit hook is a THIRD place holding a pytest command (F022).

    It advertises itself as ``task test:backend:unit:fast``, so its marker
    expression must be that task's, not a paraphrase. Until 2026-07-25 it read
    ``not integration and not slow`` — the same set as the task by measurement
    (zero e2e/benchmark/multiprocess tests live under ``tests/unit``), but the
    first one added would have run in the hook and in no CI job at all.
    """
    hook_exprs = _markers_by_root(PRE_COMMIT_HOOK.read_text(encoding="utf-8")).get("unit")
    assert hook_exprs, "the pre-commit hook no longer runs a pytest tests/unit/ command"

    task_exprs = {
        expr
        for expr in _markers_by_root(TASKFILE.read_text(encoding="utf-8"))["unit"]
        if not _is_integration_only(expr)
    }

    assert hook_exprs <= task_exprs, (
        "the pre-commit hook's -m expression diverges from the Taskfile's unit "
        f"selection (F022). Hook: {[sorted(e) for e in hook_exprs]}, "
        f"Taskfile: {[sorted(e) for e in task_exprs]}. A hook that selects MORE "
        "than the task runs tests no CI job runs; one that selects less gives "
        "false confidence before a commit."
    )


# One or more ``tests...`` paths after the runner. Written as "first path, then
# whitespace-separated others" rather than "(path + whitespace)+" so a command
# ENDING on its path (``pytest tests/unit/``, no flags) still matches — that
# spelling was invisible to the first version of this guard.
_PYTEST_PATHS = re.compile(_RUNNER + r"\s+(tests\S*(?:\s+tests\S*)*)")


def _collection_identity(command: str) -> tuple[str, str] | None:
    """Reduce a pytest command to what it actually SELECTS.

    Flags that change reporting (``-v``, ``--tb=short``) are deliberately
    excluded: two commands differing only there run the same tests twice.

    Args:
        command: A shell command line from the Taskfile.

    Returns:
        ``(paths, marker_expression)``, or None when the command is not a pytest
        invocation over a test path.
    """
    paths_match = _PYTEST_PATHS.search(command)
    if not paths_match:
        return None
    paths = " ".join(sorted(paths_match.group(1).split()))
    marker = re.search(r'-m\s+"([^"]+)"', command)
    return paths, marker.group(1) if marker else ""


def test_no_task_runs_the_same_collection_twice() -> None:
    """A task must not repeat a collection it already runs (2026-07-25).

    Task executes every matching ``cmd`` in order, so a duplicated invocation is
    pure wasted time — and since ci.yml now CALLS these tasks, the waste is paid
    on every build too. Platforms are part of the identity: the Windows and
    Unix spellings of one command are alternatives, not repetitions.
    """
    data = yaml.safe_load(TASKFILE.read_text(encoding="utf-8"))

    offenders: list[str] = []
    for task_name, body in (data.get("tasks") or {}).items():
        if not isinstance(body, dict):
            continue
        seen: dict[tuple[str, str, str], int] = {}
        for entry in body.get("cmds") or []:
            command = entry.get("cmd", "") if isinstance(entry, dict) else entry
            if not isinstance(command, str):
                continue
            identity = _collection_identity(command)
            if identity is None:
                continue
            platforms = ",".join(
                sorted(entry.get("platforms", ["all"]) if isinstance(entry, dict) else ["all"])
            )
            key = (platforms, *identity)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 2:
                offenders.append(
                    f'{task_name} [{platforms}]: pytest {identity[0]} -m "{identity[1]}"'
                )

    # ASCII only in the message: it is read on a Windows console whose default
    # code page turns typographic dashes into mojibake (same reason as
    # scripts/audit/check_code_hygiene.py).
    assert not offenders, (
        "these tasks run an identical pytest collection more than once, so every "
        f"run (local AND CI, which calls these tasks) pays for it twice: {offenders}. "
        "Delete the duplicate; if two passes are genuinely wanted, make them differ "
        "in what they select, not only in how they report."
    )


def test_coverage_threshold_has_a_single_source_of_truth() -> None:
    """Every executable copy of ``--cov-fail-under`` must equal pyproject's default.

    The coverage threshold is one governed number (ratchet doctrine), not several
    that can silently drift.

    This guard was VACUOUS from ADR-151 until 2026-08-27. It compared
    ``pyproject.toml`` against ``ci.yml`` only — and ADR-151 had moved every
    pytest command out of the workflow into ``Taskfile.yml``, so the loop
    iterated over an empty list and the assertion never ran. The Taskfile's own
    two copies of the value were, in consequence, guarded by nothing.

    The Taskfile is therefore scanned first, and a non-vacuity assertion makes
    the same disappearance impossible to repeat: if the commands move again, the
    guard fails instead of quietly approving.
    """
    pyproject_vals = _COV_FAIL_UNDER.findall(PYPROJECT.read_text(encoding="utf-8"))
    assert len(set(pyproject_vals)) == 1, (
        "pyproject.toml must define exactly one --cov-fail-under (source of truth); "
        f"found: {pyproject_vals}"
    )
    source = pyproject_vals[0]

    copies: list[tuple[str, str]] = []
    for name, path in (("Taskfile.yml", TASKFILE), ("ci.yml", CI_WORKFLOW)):
        copies.extend(
            (name, value) for value in _COV_FAIL_UNDER.findall(path.read_text(encoding="utf-8"))
        )

    assert copies, (
        "no --cov-fail-under found in Taskfile.yml or ci.yml, so this guard would "
        "compare nothing. The gated coverage command has moved (or lost its "
        "threshold): point this guard at wherever it now lives before shipping."
    )

    drifted = [(name, value) for name, value in copies if value != source]
    assert not drifted, (
        f"--cov-fail-under drifts from pyproject's {source} (F022): "
        + ", ".join(f"{name} carries {value}" for name, value in drifted)
        + ". Update them together, or drive the command from the pyproject default."
    )


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
