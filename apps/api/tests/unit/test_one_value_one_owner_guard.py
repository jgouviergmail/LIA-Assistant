"""A version written in several files has one owner, and the copies are held to it.

Doctrine 1 of the dependency programme: a version is a claim with an owner; every
other place reads it or is held equal to it by a guard. Before this guard the pnpm
version lived in four files and the promtool version in three, kept equal by
reviewers' memory — and a pnpm version that differs between the workspace and the
image is a lockfile the image may not install (``ERR_PNPM_LOCKFILE_CONFIG_MISMATCH``),
a promtool that differs from the production Prometheus validates rules on another
PromQL engine (the same rule passed on 2.53.2 and failed on 3.0.0). Since lot 7 the
API image's pinned downloads have copies too: the development image and the local
model script repeat them, and the Node tarball, which no updater reads, follows the
sandbox's Node image, which Dependabot moves.
"""

from __future__ import annotations

import ast
import json
import re

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _args(dockerfile: str) -> dict[str, str]:
    """A Dockerfile's ``ARG NAME=default`` declarations."""
    return dict(re.findall(r"^ARG\s+(\w+)=(\S*)\s*$", _read(dockerfile), re.MULTILINE))


def _string_constant(module: str, name: str) -> str:
    """A module-level string constant, read without importing the module."""
    for node in ast.parse(_read(module)).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str), f"{module}: {name} is not a string"
            return value
    raise AssertionError(f"{module} no longer declares {name}")


def _bases(dockerfile: str) -> set[str]:
    """The images a Dockerfile's stages start from (a bare stage name is not one)."""
    return {
        ref
        for ref in re.findall(r"^FROM\s+(\S+)", _read(dockerfile), re.MULTILINE)
        if ":" in ref or "@" in ref
    }


def test_the_pnpm_the_images_activate_is_the_workspace_s() -> None:
    owner = json.loads(_read("package.json"))["packageManager"].removeprefix("pnpm@")
    copies = {
        name: re.findall(r"corepack prepare pnpm@(\S+)", _read(name))
        for name in ("apps/web/Dockerfile.prod", "apps/web/Dockerfile.dev")
    }

    assert all(copies.values()), f"a web Dockerfile no longer activates pnpm by version: {copies}"
    assert {v for found in copies.values() for v in found} == {
        owner
    }, f"package.json pins pnpm@{owner} (the owner); the images activate {copies}"


def test_the_uv_the_workflows_install_is_the_lock_writer() -> None:
    """Taskfile.yml owns the uv version (deps:lock refuses any other); a workflow
    installing a different one would run the supply-chain tools on another resolver,
    and the development image installs its lock with it."""
    owner = re.search(r"^\s+UV_VERSION:\s*(\S+)", _read("Taskfile.yml"), re.MULTILINE)
    assert owner, "Taskfile.yml no longer declares UV_VERSION"
    copies = {
        path.name: found
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        if (found := re.findall(r"pip install uv==(\S+)", path.read_text(encoding="utf-8")))
    }
    image = re.findall(r"pip install uv==(\S+)", _read("apps/api/Dockerfile.dev"))

    assert copies, "no workflow installs uv any more: this guard reads nothing"
    assert image, "apps/api/Dockerfile.dev no longer installs uv by version"
    assert {v for found in [*copies.values(), image] for v in found} == {
        owner.group(1)
    }, f"Taskfile.yml pins uv {owner.group(1)}; the workflows install {copies}, the image {image}"


def test_the_dev_api_image_downloads_what_production_downloads() -> None:
    """Dockerfile.dev repeats Dockerfile.prod's downloads (the Whisper revision and
    checksums, Silero, Node, the Docker key, the Claude Code CLI): every value both
    declare is the production one, both start from the same Python image, and the
    local download script fetches the same revision."""
    prod, dev = _args("apps/api/Dockerfile.prod"), _args("apps/api/Dockerfile.dev")
    shared = prod.keys() & dev.keys()
    expected = {"HF_BASE_URL", "NODE_VERSION", "DOCKER_GPG_SHA256", "CLAUDE_CODE_VERSION"}
    assert expected <= shared, f"a pinned input left one of the two files: {expected - shared}"
    assert {name: dev[name] for name in sorted(shared)} == {
        name: prod[name] for name in sorted(shared)
    }, "apps/api/Dockerfile.dev must download exactly what Dockerfile.prod downloads"
    assert _bases("apps/api/Dockerfile.dev") == _bases("apps/api/Dockerfile.prod")

    script = re.search(r'^HF_BASE_URL="([^"]+)"', _read("scripts/download-whisper-model.sh"), re.M)
    assert script, "scripts/download-whisper-model.sh no longer declares HF_BASE_URL"
    assert script.group(1) == prod["HF_BASE_URL"]


def test_the_local_secret_scan_runs_the_ci_s_gitleaks() -> None:
    """`task security:secrets` (and the pre-push hook that calls it) is the twin of the
    CI's Secret Scan, a `uses:` step nobody can run: a twin on another version reads
    other rules, so the version is written in both places and held equal here."""
    workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
    steps = workflow["jobs"]["secret-scan"]["steps"]
    action = [s for s in steps if "gitleaks/gitleaks-action" in str(s.get("uses", ""))]
    assert len(action) == 1, "the CI's secret-scan job no longer runs the gitleaks action once"
    owner = str((action[0].get("env") or {}).get("GITLEAKS_VERSION", ""))
    assert owner, "the CI's gitleaks step no longer pins GITLEAKS_VERSION"
    copies = re.findall(
        r"zricethezav/gitleaks:v(\d+\.\d+\.\d+)@sha256:[0-9a-f]{64}", _read("Taskfile.yml")
    )

    assert copies, "Taskfile.yml no longer runs a gitleaks image pinned by version and digest"
    assert set(copies) == {owner}, f"the CI scans with gitleaks {owner}, Taskfile.yml with {copies}"


def test_tests_start_the_database_production_runs() -> None:
    """The Testcontainers fallback of tests/conftest.py starts the production image:
    a test that passes on another engine says nothing about the one that ships."""
    production = yaml.safe_load(_read("docker-compose.prod.yml"))["services"]["postgres"]
    fallback = _string_constant("apps/api/tests/conftest.py", "TESTCONTAINERS_POSTGRES_IMAGE")
    assert fallback == production["image"]


def test_the_api_image_unpacks_the_node_the_sandbox_runs() -> None:
    """Nothing moves an ARG by itself: Dockerfile.prod's Node tarball follows the
    sandbox's Node stage, which Dependabot moves — its pull request (same directory)
    cannot merge until the version and both checksums follow."""
    sandbox = re.search(
        r"^FROM node:(\d+\.\d+\.\d+)-\S+@sha256:", _read("apps/api/Dockerfile.sandbox"), re.M
    )
    assert sandbox, "Dockerfile.sandbox no longer starts a stage from a pinned node image"
    owner, copy = sandbox.group(1), _args("apps/api/Dockerfile.prod").get("NODE_VERSION")
    assert copy == owner, (
        f"the sandbox runs Node {owner}, Dockerfile.prod unpacks {copy}: set NODE_VERSION and "
        f"both NODE_SHA256_* from https://nodejs.org/dist/v{owner}/SHASUMS256.txt"
    )


def test_promtool_validates_on_the_prometheus_production_runs() -> None:
    services = yaml.safe_load(_read("docker-compose.prod.yml"))["services"]
    match = re.fullmatch(
        r"prom/prometheus:v(\d+\.\d+\.\d+)(?:@sha256:[0-9a-f]{64})?",
        services["prometheus"]["image"],
    )
    assert match, services["prometheus"]["image"]
    owner = match.group(1)
    copies = {
        ".github/workflows/ci.yml": re.findall(
            r"^\s*VER=(\S+)\s*$", _read(".github/workflows/ci.yml"), re.MULTILINE
        ),
        "Taskfile.yml": re.findall(r"prom/prometheus:v(\d+\.\d+\.\d+)", _read("Taskfile.yml")),
    }

    assert all(copies.values()), f"a promtool pin is no longer where this guard reads it: {copies}"
    assert {v for found in copies.values() for v in found} == {
        owner
    }, f"production runs Prometheus {owner}; promtool is pinned at {copies}"
