"""Self-host Compose contract (B04/B15, ADR-215).

What must hold:
- app images are parameterized (`LIA_API_IMAGE`/`LIA_WEB_IMAGE`) with the
  historical local defaults, and the skills sandbox image derives from the
  SAME variable — substituting a prebuilt API image can never leave the
  sandbox on a different image;
- exactly the 5 core services carry no profile; exactly the 12
  observability/management services carry only ["observability"];
- the BASE api service holds no Docker socket, no group_add, and no
  maintainer Claude mount; script skills default OFF in base;
- the skill-sandbox overlay adds socket + group_add + scripts ON;
- the devops overlay adds only the two maintainer Claude mounts;
- the Bash deploy helper lets Compose parse its native colon-separated
  COMPOSE_FILE (never wraps the value in one -f).
"""

from __future__ import annotations

import re

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit
ROOT = repo_root_or_skip()

CORE_SERVICES = {"postgres", "postgres-backup", "redis", "api", "web"}
OBSERVABILITY_SERVICES = {
    "tempo",
    "prometheus",
    "alertmanager",
    "blackbox-exporter",
    "grafana",
    "loki",
    "promtail",
    "node-exporter",
    "cadvisor",
    "postgres-exporter",
    "redis-exporter",
    "portainer",
}


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


def test_app_images_are_parameterized_with_local_defaults() -> None:
    services = _load("docker-compose.prod.yml")["services"]
    assert services["api"]["image"] == "${LIA_API_IMAGE:-lia-api:local}"
    assert services["web"]["image"] == "${LIA_WEB_IMAGE:-lia-web:local}"
    env = services["api"]["environment"]
    assert "SKILLS_SCRIPT_SANDBOX_IMAGE=${LIA_API_IMAGE:-lia-api:local}" in env
    assert "SKILLS_SCRIPTS_ENABLED=${SKILLS_SCRIPTS_ENABLED:-false}" in env


def test_profile_split_is_exact() -> None:
    services = _load("docker-compose.prod.yml")["services"]
    assert set(services) == CORE_SERVICES | OBSERVABILITY_SERVICES
    for name, svc in services.items():
        if name in CORE_SERVICES:
            assert "profiles" not in svc, f"core service {name} must not carry a profile"
        else:
            assert svc.get("profiles") == [
                "observability"
            ], f"service {name} must carry exactly ['observability']"


def test_base_api_has_no_privileged_surface() -> None:
    api = _load("docker-compose.prod.yml")["services"]["api"]
    volumes = api.get("volumes", [])
    joined = " ".join(volumes)
    assert "docker.sock" not in joined
    assert ".claude" not in joined
    assert "claude-cli" not in joined
    assert "group_add" not in api


def test_skill_sandbox_overlay_owns_the_socket() -> None:
    overlay = _load("docker-compose.skill-sandbox.yml")["services"]["api"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in overlay["volumes"]
    assert "group_add" in overlay
    assert "SKILLS_SCRIPTS_ENABLED=true" in overlay["environment"]


def test_devops_overlay_contains_only_the_claude_mounts() -> None:
    overlay = _load("docker-compose.devops.yml")["services"]["api"]
    assert overlay["volumes"] == [
        "~/.claude:/home/appuser/.claude",
        "./infrastructure/claude-cli/CLAUDE.server.md:/opt/claude-workspace/CLAUDE.md:ro",
    ]
    assert set(overlay) == {"volumes"}


def test_deploy_helper_uses_native_compose_file_parsing() -> None:
    body = (ROOT / "scripts/deploy/lib/deploy_readiness_gate.sh").read_text(encoding="utf-8")
    assert not re.search(r'-f\s+"\$COMPOSE_FILE"', body), (
        "a colon-separated COMPOSE_FILE wrapped in one -f is an invalid filename;"
        " let Compose parse the variable natively"
    )
    assert 'COMPOSE_FILE="$COMPOSE_FILE" docker compose' in body


def test_maintainer_default_compose_chain_preserves_behavior() -> None:
    body = (ROOT / "scripts/deploy/lib/deploy_readiness_gate.sh").read_text(encoding="utf-8")
    assert (
        "docker-compose.prod.yml:docker-compose.skill-sandbox.yml:docker-compose.devops.yml" in body
    ), "the maintainer deploy keeps socket skills and Claude mounts via overlays"
