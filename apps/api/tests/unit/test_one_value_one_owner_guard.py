"""A version written in several files has one owner, and the copies are held to it.

Doctrine 1 of the dependency programme: a version is a claim with an owner; every
other place reads it or is held equal to it by a guard. Before this guard the pnpm
version lived in four files and the promtool version in three, kept equal by
reviewers' memory — and a pnpm version that differs between the workspace and the
image is a lockfile the image may not install (``ERR_PNPM_LOCKFILE_CONFIG_MISMATCH``),
a promtool that differs from the production Prometheus validates rules on another
PromQL engine (the same rule passed on 2.53.2 and failed on 3.0.0).
"""

from __future__ import annotations

import json
import re

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


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
    installing a different one would run the supply-chain tools on another resolver."""
    owner = re.search(r"^\s+UV_VERSION:\s*(\S+)", _read("Taskfile.yml"), re.MULTILINE)
    assert owner, "Taskfile.yml no longer declares UV_VERSION"
    copies = {
        path.name: found
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
        if (found := re.findall(r"pip install uv==(\S+)", path.read_text(encoding="utf-8")))
    }

    assert copies, "no workflow installs uv any more: this guard reads nothing"
    assert {v for found in copies.values() for v in found} == {
        owner.group(1)
    }, f"Taskfile.yml pins uv {owner.group(1)}; the workflows install {copies}"


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
