"""Every Python-version surface tracks the requires-python floor (single-version contract).

The 3.12→3.14 migration audit (2026-07-29, re-verified 2026-08-20) found the interpreter
version encoded in six independent surfaces: pyproject, both API Dockerfiles, the uv
compile flags, the skills sandbox PYTHONPATH (constant + .env examples), and the CI
workflows. A future bump that misses one ships a mixed-version system — the sandbox then
mounts a dead site-packages path (the v1.25.25 `.env` failure class). All checks key off
the pyproject floor so there is exactly one source of truth (ADR-241).

Exception: the ADR-215 self-host installer wizard runs on bare operator hosts and keeps
its own Python 3.10 floor (ci.yml job "Installer Python 3.10 floor") — it is exempted
below, narrowly, and its floor is asserted so a silent drift there is caught too.
"""

from __future__ import annotations

import re
import sys
import tomllib

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
API_DIR = REPO_ROOT / "apps" / "api"

# ADR-215: the installer wizard gate deliberately runs on the bare 3.10 interpreter.
INSTALLER_FLOOR = "3.10"
INSTALLER_STEP_MARKER = "scripts/install/tests_py310.py"


def _floor() -> str:
    """Return the requires-python floor as 'major.minor' (e.g. '3.14')."""
    data = tomllib.loads((API_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    match = re.search(r">=\s*(3\.\d+)", data["project"]["requires-python"])
    assert match, "requires-python must declare a >= floor"
    return match.group(1)


def test_interpreter_matches_contract() -> None:
    """The suite must run on the contract's interpreter (catches venv/container drift)."""
    running = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert running == _floor(), (
        f"test run on Python {running} but the contract floor is {_floor()} — "
        "recreate the environment (single-version contract, ADR-241)"
    )


def test_dockerfiles_track_the_floor() -> None:
    """Every python base image in both API Dockerfiles carries the contract version."""
    floor = _floor()
    for name in ("Dockerfile.dev", "Dockerfile.prod"):
        text = (API_DIR / name).read_text(encoding="utf-8")
        tags = re.findall(r"^FROM python:(\d+\.\d+)-", text, re.MULTILINE)
        assert tags, f"{name}: no python base image found"
        assert set(tags) == {floor}, f"{name}: FROM versions {sorted(set(tags))} != {floor}"


def test_uv_compile_flags_track_the_floor() -> None:
    """`task deps:lock` must compile the universal lock on the contract floor."""
    taskfile = (REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8")
    match = re.search(r"UV_COMPILE_FLAGS:.*--python-version\s+(\d+\.\d+)", taskfile)
    assert match, "UV_COMPILE_FLAGS with --python-version not found in Taskfile.yml"
    assert match.group(1) == _floor()


def test_sandbox_pythonpath_tracks_the_floor() -> None:
    """The skills-sandbox site-packages path embeds the contract interpreter version."""
    from src.core.constants import SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT

    floor = _floor()
    assert f"/python{floor}/" in SKILLS_SCRIPT_SANDBOX_PYTHONPATH_DEFAULT
    for env_example in (REPO_ROOT / ".env.example", REPO_ROOT / ".env.prod.example"):
        line = next(
            ln
            for ln in env_example.read_text(encoding="utf-8").splitlines()
            if ln.startswith("SKILLS_SCRIPT_SANDBOX_PYTHONPATH=")
        )
        assert f"/python{floor}/" in line, f"{env_example.name}: sandbox path drifted"


def test_all_workflow_python_versions_match_contract() -> None:
    """No workflow may set up an out-of-contract Python, except the ADR-215 installer
    gate (bare-host wizard, own 3.10 floor). Extends the F041 guard, which only proves
    ci.yml COVERS the range — security.yml/release.yml were previously unchecked."""
    floor = _floor()
    for workflow in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        versions = re.findall(r'python-version:\s*"(3\.\d+)"', text)
        allowed = {floor}
        if INSTALLER_STEP_MARKER in text:
            allowed.add(INSTALLER_FLOOR)
            assert versions.count(INSTALLER_FLOOR) == 1, (
                f"{workflow.name}: the {INSTALLER_FLOOR} installer floor must appear "
                "exactly once (ADR-215)"
            )
        extra = set(versions) - allowed
        assert not extra, f"{workflow.name}: out-of-contract python-version {sorted(extra)}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
