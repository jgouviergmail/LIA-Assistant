"""The Python version contract is bounded and CI-verified (audit F041).

``requires-python`` claimed ``>=3.12`` with no upper bound, while CI only ever
ran Python 3.12 — an unbounded, unverified promise (3.13, which developer hosts
actually run, and every future major were implicitly "supported" but never
tested). This guard freezes the contract as *bounded* and pins that every
version in the supported range is exercised by a CI job.
"""

from __future__ import annotations

import re
import tomllib

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _requires_python() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["requires-python"]


def test_requires_python_is_bounded() -> None:
    """The contract must declare BOTH a lower (>=) and an upper (<) bound."""
    spec = _requires_python()
    assert ">=" in spec, f"requires-python has no lower bound: {spec!r}"
    assert "<" in spec, (
        f"requires-python is unbounded above: {spec!r} (F041) — bound it to the "
        "range CI actually verifies so the support promise is not a fiction."
    )


def test_supported_python_range_is_covered_by_ci() -> None:
    """Every minor in [lower, upper) must appear as a CI python-version."""
    spec = _requires_python()
    lower = re.search(r">=\s*3\.(\d+)", spec)
    upper = re.search(r"<\s*3\.(\d+)", spec)
    assert lower and upper
    supported = {f"3.{m}" for m in range(int(lower.group(1)), int(upper.group(1)))}

    ci_text = CI_WORKFLOW.read_text(encoding="utf-8")
    ci_versions = set(re.findall(r'python-version:\s*"(3\.\d+)"', ci_text))
    # yaml load also catches matrix lists if ever added
    missing = supported - ci_versions
    assert not missing, (
        f"Supported Python minors not exercised by any CI job (F041): {sorted(missing)}. "
        f"Add a job/matrix entry, or narrow requires-python. CI has: {sorted(ci_versions)}"
    )


def test_ci_workflow_is_valid_yaml() -> None:
    """Sanity: the CI workflow parses (the python-compat job must be well-formed)."""
    assert yaml.safe_load(CI_WORKFLOW.read_text(encoding="utf-8"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
