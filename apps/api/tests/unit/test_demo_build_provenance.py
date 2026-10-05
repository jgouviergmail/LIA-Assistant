"""Render the real demo envelope with the command the production driver builds."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()
IDENTITY = {
    "APP_VERSION": "9.9.9-test",
    "GIT_COMMIT_SHA": "abcdef0123456789abcdef0123456789abcdef01",
    "BUILD_DATE": "2026-10-04T12:00:00Z",
}


def _bash() -> str:
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
        if candidate.is_file():
            return str(candidate)
    shell = shutil.which("bash")
    if shell is None:
        pytest.skip("Bash is required to execute the remote Compose command")
    return shell


def _production_command() -> str:
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell is required to evaluate the driver's Compose assignment")
    driver = (ROOT / "scripts/deploy/demo-prod.ps1").as_posix()
    # Evaluate this assignment only: no private config, SSH, or driver action.
    script = (
        "$errors = $null; "
        "$ast = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{driver}', [ref]$null, [ref]$errors); "
        "if ($errors.Count) { exit 1 }; "
        "$assignments = @($ast.FindAll({ param($node) "
        "$node -is [System.Management.Automation.Language.AssignmentStatementAst] "
        "-and $node.Left.Extent.Text -eq '$Compose' }, $true)); "
        "if ($assignments.Count -ne 1) { exit 2 }; "
        "$seedDigest = '" + "a" * 64 + "'; "
        "Invoke-Expression $assignments[0].Extent.Text; "
        "[Console]::Write($Compose)"
    )
    result = subprocess.run(
        [shell, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout


def _render(tmp_path: Path, *, production: bool, provenance: bool = True):
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is required; config does not use a daemon")
    compose = (ROOT / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")
    (tmp_path / "docker-compose.demo-instance.yml").write_text(compose, encoding="utf-8")
    values = {
        "DEMO_INSTANCE_POSTGRES_PASSWORD": "fixture-password",
        "DEMO_INSTANCE_SMTP_SMARTHOST": "mail.example.test",
        "ALERTMANAGER_SMTP_AUTH_USERNAME": "fixture-user",
        "ALERTMANAGER_SMTP_AUTH_PASSWORD": "fixture-password",
        "DEMO_INSTANCE_MAIL_DOMAIN": "example.test",
        "APP_URL_SERVER": "https://demo.example.test",
    }
    if production:
        # env_file overrides image ENV unless Compose explicitly carries identity.
        values.update(dict.fromkeys(IDENTITY, "stale-private-profile"))
    (tmp_path / ".env.demo-instance.prod").write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8"
    )
    if production and provenance:
        (tmp_path / "provenance.env").write_text(
            "\n".join(f"export {key}={value}" for key, value in IDENTITY.items()) + "\n",
            encoding="utf-8",
        )
    command = (
        _production_command()
        if production
        else "DEMO_INSTANCE_ENV_FILE=.env.demo-instance.prod "
        "docker compose --env-file .env.demo-instance.prod -f docker-compose.demo-instance.yml"
    )
    env = os.environ.copy()
    for name in re.findall(r"\$\{([A-Z0-9_]+)", compose):
        env.pop(name, None)
    for name in ("COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_PROJECT_NAME"):
        env.pop(name, None)
    env["MSYS_NO_PATHCONV"] = "1"
    return subprocess.run(
        [_bash(), "--noprofile", "--norc", "-c", command + " config --format json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_demo_production_uses_bundle_identity_for_build_and_runtime(tmp_path: Path) -> None:
    result = _render(tmp_path, production=True)
    assert result.returncode == 0, result.stderr
    api = json.loads(result.stdout)["services"]["demo-instance-api"]
    for key, expected in IDENTITY.items():
        assert api["build"]["args"][key] == expected
        assert api["environment"][key] == expected


def test_local_demo_without_bundle_has_explicit_development_identity(tmp_path: Path) -> None:
    result = _render(tmp_path, production=False)
    assert result.returncode == 0, result.stderr
    api = json.loads(result.stdout)["services"]["demo-instance-api"]
    for key, expected in {
        "APP_VERSION": "0.0.0-dev",
        "GIT_COMMIT_SHA": "unknown",
        "BUILD_DATE": "unknown",
    }.items():
        assert api["build"]["args"][key] == expected
        assert api["environment"][key] == expected


def test_demo_production_refuses_missing_bundle_provenance(tmp_path: Path) -> None:
    result = _render(tmp_path, production=True, provenance=False)
    assert result.returncode != 0
    assert "provenance.env" in result.stderr
    assert not result.stdout.strip()
