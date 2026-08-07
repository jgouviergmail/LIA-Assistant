"""Installer CI parity contract (ADR-215, B01/B15).

The hermetic installer proof must be a NORMAL-CI gate:

- the five Task targets exist with platform-correct venv paths;
- a dedicated CI step runs exactly ``task test:install:hermetic``;
- ``test:install:hermetic`` delegates to the four component targets plus
  the focused backend suites of Tasks 2/7/8/9;
- a separate normal-CI job pins ``actions/setup-python`` to exact ``3.10``
  and runs ``python -B scripts/install/tests_py310.py``;
- no installer step declares ``continue-on-error``.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

TARGETS = (
    "test:install:",
    "lint:install:",
    "test:install:compose-matrix:",
    "test:release:self-host:",
    "test:install:hermetic:",
)


def _taskfile() -> str:
    return (repo_root_or_skip() / "Taskfile.yml").read_text(encoding="utf-8")


def _ci() -> str:
    return (repo_root_or_skip() / ".github/workflows/ci.yml").read_text(encoding="utf-8")


def test_all_five_targets_exist() -> None:
    body = _taskfile()
    for target in TARGETS:
        assert f"\n  {target}" in body, f"missing Task target {target}"


def test_targets_use_platform_correct_venv_paths() -> None:
    body = _taskfile()
    install_block = body.split("\n  test:install:", 1)[1]
    assert ".venv/Scripts/pytest" in install_block
    assert ".venv/bin/pytest" in install_block


def test_hermetic_target_delegates_to_components_and_backend_suites() -> None:
    body = _taskfile()
    hermetic = body.split("\n  test:install:hermetic:", 1)[1].split("\n  test", 1)[0]
    for needle in (
        "task: test:install",
        "task: lint:install",
        "task: test:install:compose-matrix",
        "task: test:release:self-host",
        "task: test:install:backend-contracts",
    ):
        assert needle in hermetic, f"hermetic target misses {needle}"
    contracts = body.split("\n  test:install:backend-contracts:", 1)[1].split("\n  test:", 1)[0]
    for needle in (
        "test_validate_settings_script",
        "test_reference_seed_bundle_contract",
        "test_bootstrap_install_contract",
        "test_verify_installation_script",
        "test_installer_wizard_backend_alignment",
    ):
        assert needle in contracts, f"backend-contracts target misses {needle}"


def test_ci_runs_the_hermetic_gate_verbatim() -> None:
    assert re.search(r"run:\s+task test:install:hermetic\s*$", _ci(), re.M)


def test_ci_has_the_dedicated_python310_job() -> None:
    ci = _ci()
    job_match = re.search(r"installer-py310:.*?(?=\n  [a-z0-9_-]+:|\Z)", ci, re.S)
    assert job_match, "missing installer-py310 job"
    job = job_match.group(0)
    assert 'python-version: "3.10"' in job
    assert "python -B scripts/install/tests_py310.py" in job
    assert "continue-on-error" not in job


def test_no_installer_step_is_soft_failed() -> None:
    ci = _ci()
    for anchor in ("test:install:hermetic", "tests_py310"):
        index = ci.index(anchor)
        window = ci[max(0, index - 400) : index + 400]
        assert "continue-on-error" not in window
