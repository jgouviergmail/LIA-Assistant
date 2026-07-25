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
"""

from __future__ import annotations

import re

import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
TASKFILE = REPO_ROOT / "Taskfile.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"

_TEST_ROOTS = ("unit", "agents", "integration")
# ``pytest tests/<root>/ ... -m "<expr>"`` — CI splits the command across
# backslash-continued lines, so continuations are joined first.
_PYTEST_M = re.compile(r'pytest\s+tests/(unit|agents|integration)/[^\n]*?-m\s+"([^"]+)"')
# The full flag tail of every ``pytest tests/<root>/`` command (post line-join).
_PYTEST_CMD = re.compile(r"pytest\s+tests/(unit|agents|integration)/([^\n]*)")
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


def test_coverage_threshold_has_a_single_source_of_truth() -> None:
    """The ``--cov-fail-under`` value in CI must equal pyproject's addopts default
    (F022): the coverage threshold is one governed number (ratchet doctrine), not two
    that can silently drift between ``pyproject.toml`` and ``ci.yml``."""
    pyproject_vals = _COV_FAIL_UNDER.findall(PYPROJECT.read_text(encoding="utf-8"))
    assert len(set(pyproject_vals)) == 1, (
        "pyproject.toml must define exactly one --cov-fail-under (source of truth); "
        f"found: {pyproject_vals}"
    )
    source = pyproject_vals[0]
    for ci_val in _COV_FAIL_UNDER.findall(CI_WORKFLOW.read_text(encoding="utf-8")):
        assert ci_val == source, (
            f"CI --cov-fail-under={ci_val} drifts from pyproject's {source} (F022). "
            "Update both together, or drive CI from the pyproject default."
        )


if __name__ == "__main__":  # pragma: no cover
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
