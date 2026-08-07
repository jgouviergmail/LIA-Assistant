"""Disposable qualification workflow contract (ADR-215, T16 — static).

The workflow that PROVES installability on clean machines must be
structurally incapable of touching anything real:

- manual dispatch only, behind an approval environment;
- both native architectures x both install modes;
- project names locked to the lia-installer-smoke- prefix; cleanup scoped
  to that exact project, no prune, no unscoped removal;
- no dev compose file, production hostname, or real provider secret;
- hermetic provider endpoints only (fake-provider base URLs);
- login/chat probes hit the real public API paths.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit


def _workflow() -> str:
    return (repo_root_or_skip() / ".github/workflows/installer-disposable-smoke.yml").read_text(
        encoding="utf-8"
    )


def _runtime_dir() -> Path:
    return repo_root_or_skip() / "scripts/install/tests/runtime"


def test_dispatch_only_with_approval_environment() -> None:
    body = _workflow()
    assert "workflow_dispatch:" in body
    for forbidden in ("push:", "pull_request:", "schedule:", "workflow_run:", "workflow_call:"):
        assert f"\n  {forbidden}" not in body.split("jobs:")[0], forbidden
    assert "environment: installer-disposable-smoke" in body


def test_matrix_covers_both_architectures_and_modes() -> None:
    body = _workflow()
    assert "ubuntu-24.04-arm" in body
    assert re.search(r"runner:\s*ubuntu-24\.04\s*$", body, re.M)
    assert "mode: local" in body and "mode: prebuilt" in body


def test_project_prefix_is_locked_and_cleanup_is_scoped() -> None:
    body = _workflow()
    assert "lia-installer-smoke-" in body
    assert re.search(r"\^lia-installer-smoke-\[a-zA-Z0-9-\]\+\$", body)
    assert "docker system prune" not in body
    assert "docker volume prune" not in body
    cleanup = body[body.index("Cleanup") :]
    assert "-p " in cleanup or "--project-name" in cleanup


def test_no_dev_compose_prod_hostname_or_real_secret() -> None:
    body = _workflow()
    assert "docker-compose.dev.yml" not in body
    assert "lia.jeyswork.com" not in body
    # Real infra tokens must never be spelled here either (the tracked file
    # would itself leak them): reuse the git-ignored local denylist — every
    # token it holds must be absent from the workflow. Empty/absent list ->
    # the hostname assertions above still stand.
    denylist = Path(__file__).resolve().parents[1] / ".infra_denylist"
    if denylist.is_file():
        for line in denylist.read_text(encoding="utf-8").splitlines():
            token = line.split("#", 1)[0].strip()
            if token:
                assert token not in body, "workflow leaks a denylisted infra token"
    assert "secrets.OPENAI" not in body and "secrets.DEEPSEEK" not in body


def test_hermetic_provider_endpoints_and_public_probes() -> None:
    body = _workflow()
    assert "OPENAI_BASE_URL: http://fake-provider:18080/v1" in body
    assert "DEEPSEEK_BASE_URL: http://fake-provider:18080/v1" in body
    # The probes live in the runtime harness the workflow invokes.
    assert "assert_install.py" in body
    probes = (_runtime_dir() / "assert_install.py").read_text(encoding="utf-8")
    assert "/api/v1/auth/login" in probes
    assert "/api/v1/agents/chat/stream" in probes


def test_runtime_fixtures_exist() -> None:
    runtime = _runtime_dir()
    for name in (
        "docker-compose.disposable.yml",
        "fake_provider.py",
        "assert_install.py",
        "inject_seed_failure.py",
    ):
        assert (runtime / name).is_file(), name


def test_fake_provider_is_stdlib_only_and_key_gated() -> None:
    body = (_runtime_dir() / "fake_provider.py").read_text(encoding="utf-8")
    assert "/v1/models" in body
    assert "/v1/chat/completions" in body
    assert "/v1/responses" in body
    assert "sk-fake-qualification-key" in body
    for forbidden in ("import requests", "import httpx", "import fastapi"):
        assert forbidden not in body
