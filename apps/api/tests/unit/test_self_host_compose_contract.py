"""Self-host Compose contract (B04/B15, ADR-215).

What must hold:
- app images are parameterized (`LIA_API_IMAGE`/`LIA_WEB_IMAGE`) with the
  historical local defaults, and the skills sandbox image derives from the
  SAME variable — substituting a prebuilt API image can never leave the
  sandbox on a different image; the DEV compose holds the same rule against
  its own explicit tag (it pointed at the prod tag for six weeks after the
  dev image was renamed, and every sandbox run failed as "unavailable");
- exactly the 5 core services carry no profile; exactly the 12
  observability/management services carry only ["observability"];
- the BASE api service holds no Docker socket, no group_add, and no
  maintainer Claude mount; script skills default OFF in base;
- the skill-sandbox overlay adds socket + group_add + scripts ON;
- the devops overlay adds only the two maintainer Claude mounts;
- the Bash deploy helper lets Compose parse its native colon-separated
  COMPOSE_FILE (never wraps the value in one -f);
- the sandbox egress proxy (ADR-298) is the ONLY routed member of the
  ``lia-sandbox`` internal network, pinned by digest, identical in the dev
  compose and the skill-sandbox overlay, and the CA private key never reaches
  the API read-write nor the sandbox at all;
- a third-party image has ONE reference across every compose file and every
  workflow, a divergence being declared with its reason (and a declaration that
  no longer diverges failing);
- the self-host catalogue pins what production runs.
"""

from __future__ import annotations

import json
import re
from typing import Any

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


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))
    return data


def test_app_images_are_parameterized_with_local_defaults() -> None:
    services = _load("docker-compose.prod.yml")["services"]
    assert services["api"]["image"] == "${LIA_API_IMAGE:-lia-api:local}"
    assert services["web"]["image"] == "${LIA_WEB_IMAGE:-lia-web:local}"
    env = services["api"]["environment"]
    # The sandbox runs on its OWN image (ADR-327 lot 2), never the API's.
    assert "SKILLS_SCRIPT_SANDBOX_IMAGE=${LIA_SKILL_SANDBOX_IMAGE:-lia-skill-sandbox:local}" in env
    assert "SKILLS_SCRIPTS_ENABLED=${SKILLS_SCRIPTS_ENABLED:-false}" in env


def test_dev_sandbox_runs_on_the_sandbox_image_the_dev_tasks_build() -> None:
    """The dev sandbox is the image `task sandbox:image:build` tags, never the API's."""
    api = _load("docker-compose.dev.yml")["services"]["api"]
    assert "SKILLS_SCRIPT_SANDBOX_IMAGE=lia-skill-sandbox:local" in api["environment"]
    taskfile = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8"))
    tasks = taskfile["tasks"]
    assert "lia-skill-sandbox:local" in tasks["sandbox:image:build"]["vars"]["IMAGE"]
    for name in ("dev", "dev:detach", "dev:all"):
        assert {"task": "sandbox:image:build"} in tasks[name]["cmds"], name


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


# ---- Sandbox egress proxy (ADR-298) -----------------------------------------

EGRESS_COMPOSE_FILES = ("docker-compose.dev.yml", "docker-compose.skill-sandbox.yml")
SANDBOX_NETWORK = "lia-sandbox"
EGRESS_VOLUMES = ("lia-egress-ca", "lia-egress-key", "lia-egress-config")


def _mounts(service: dict) -> dict[str, str]:
    """``{volume: mode}`` for a service's named-volume mounts (mode "rw" when unstated)."""
    out: dict[str, str] = {}
    for entry in service.get("volumes", []):
        parts = entry.split(":")
        if len(parts) >= 2 and not parts[0].startswith((".", "/", "~", "$")):
            out[parts[0]] = parts[2] if len(parts) == 3 else "rw"
    return out


@pytest.mark.parametrize("compose", EGRESS_COMPOSE_FILES)
def test_egress_proxy_is_the_only_routed_member_of_the_sandbox_network(compose: str) -> None:
    doc = _load(compose)
    services = doc["services"]
    network = doc["networks"][SANDBOX_NETWORK]
    # `name:` is explicit: the API launches sandboxes with a raw `docker run
    # --network`, which cannot see a Compose-prefixed network.
    assert network["internal"] is True and network["name"] == SANDBOX_NETWORK
    on_sandbox = {
        name for name, svc in services.items() if SANDBOX_NETWORK in svc.get("networks", [])
    }
    assert on_sandbox == {"egress"}, on_sandbox
    assert set(services["egress"]["networks"]) == {SANDBOX_NETWORK, "lia-network"}


@pytest.mark.parametrize("compose", EGRESS_COMPOSE_FILES)
def test_egress_proxy_is_hardened_and_owns_its_state(compose: str) -> None:
    """The proxy generates its CA, token and bootstrap ruleset ITSELF, as its
    own uid, in its entrypoint. A separate init container was measured wrong
    (2026-09-18): it wrote into the tmpfs volume, exited, and Docker released
    the tmpfs before the proxy mounted it — the proxy started on nothing."""
    services = _load(compose)["services"]
    assert "egress-init" not in services
    egress = services["egress"]
    assert egress["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in egress["security_opt"]
    assert egress["read_only"] is True
    assert "user" in egress
    assert egress["entrypoint"] == ["/bin/sh", "/opt/lia-egress/entrypoint.sh"]
    mounts = _mounts(egress)
    assert mounts == dict.fromkeys(EGRESS_VOLUMES, "rw"), mounts
    assert "./infrastructure/sandbox-egress:/opt/lia-egress:ro" in egress["volumes"]


def test_egress_image_is_pinned_by_digest_and_identical_everywhere() -> None:
    images = {
        compose: _load(compose)["services"]["egress"]["image"] for compose in EGRESS_COMPOSE_FILES
    }
    assert len(set(images.values())) == 1, images
    image = next(iter(images.values()))
    assert re.fullmatch(r"ironsh/iron-proxy:\d+\.\d+\.\d+@sha256:[0-9a-f]{64}", image), image


@pytest.mark.parametrize("compose", EGRESS_COMPOSE_FILES)
def test_egress_volumes_are_named_and_never_touch_the_disk(compose: str) -> None:
    """Three tmpfs volumes: the CA key, the ruleset and the per-run secrets live
    in memory only and vanish with the stack — a CA is minted at every boot."""
    volumes = _load(compose)["volumes"]
    for name in EGRESS_VOLUMES:
        assert volumes[name]["name"] == name, name
        assert volumes[name]["driver_opts"]["type"] == "tmpfs", name


@pytest.mark.parametrize("compose", EGRESS_COMPOSE_FILES)
def test_api_writes_the_ruleset_and_never_holds_the_ca_key(compose: str) -> None:
    api = _load(compose)["services"]["api"]
    mounts = _mounts(api)
    assert mounts.get("lia-egress-config") == "rw"
    # The management token lives in the (tmpfs) config volume, so the API never
    # mounts the volume holding the CA private key — not even read-only.
    assert "lia-egress-key" not in mounts
    assert "lia-egress-ca" not in mounts
    assert SANDBOX_NETWORK not in api.get("networks", [])
    assert "PYTHON_SANDBOX_EGRESS_ENABLED=true" in api["environment"]


def test_prometheus_probes_the_egress_proxy_health() -> None:
    """iron-proxy 0.49 exposes no Prometheus series (measured: /metrics is 404,
    /healthz answers OK), so liveness goes through the blackbox exporter like
    the backup sidecar's."""
    prom = yaml.safe_load(
        (ROOT / "infrastructure/observability/prometheus/prometheus.yml").read_text(
            encoding="utf-8"
        )
    )
    jobs = {job["job_name"]: job for job in prom["scrape_configs"]}
    job = jobs["blackbox-egress"]
    assert job["metrics_path"] == "/probe"
    assert job["static_configs"][0]["targets"] == ["http://egress:9094/healthz"]
    assert any(r.get("replacement") == "blackbox-exporter:9115" for r in job["relabel_configs"])


#: Every compose file of the repository (the root ones discovered, so a new one is
#: read), and every workflow's services and containers: one third-party image, one
#: reference (the generalisation of the egress pin above, dependency lot 3).
_NESTED_COMPOSE_FILES = (
    "infrastructure/docker/compose.services.yml",
    "scripts/install/tests/runtime/docker-compose.disposable.yml",
)
#: References allowed to differ from the rest of their image, and why.
_DIVERGENT_BY_DESIGN = {
    ("docker-compose.dev.yml", "langfuse-redis"): (
        "Langfuse's own cache in the dev observability profile, which follows Langfuse's "
        "support matrix and sits outside the dependency programme (decision D2)"
    ),
}


def _image_references() -> list[tuple[tuple[str, str], str]]:
    """``((file, service or job), image)`` for every literal image reference."""
    found: list[tuple[tuple[str, str], str]] = []
    compose_files = [p.name for p in sorted(ROOT.glob("docker-compose*.yml"))]
    for name in [*compose_files, *_NESTED_COMPOSE_FILES]:
        for service, spec in (_load(name).get("services") or {}).items():
            image = (spec or {}).get("image")
            if image and not image.startswith("${"):
                found.append(((name, service), image))
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for job_name, job in (_load(f".github/workflows/{path.name}")["jobs"]).items():
            for service_name, service in (job.get("services") or {}).items():
                found.append(((path.name, f"{job_name}/{service_name}"), service["image"]))
            container = job.get("container")
            if isinstance(container, dict) and container.get("image"):
                found.append(((path.name, job_name), container["image"]))
    return found


def _repository(image: str) -> str:
    return re.split(r"[:@]", image, maxsplit=1)[0]


def test_a_third_party_image_has_one_reference_everywhere() -> None:
    """A service the production compose runs is tested and developed on that same image.

    A different tag in CI or in dev is a different engine: the CI's Redis was
    ``redis:7-alpine`` while production, the demonstrator and the shared services ran
    ``redis:7.4-alpine`` (found by this test when it was written).
    """
    found = _image_references()
    references: dict[str, dict[str, list[str]]] = {}
    for (where, what), image in found:
        if (where, what) not in _DIVERGENT_BY_DESIGN:
            references.setdefault(_repository(image), {}).setdefault(image, []).append(
                f"{where}:{what}"
            )

    divergent = {repo: refs for repo, refs in references.items() if len(refs) > 1}
    assert not divergent, f"one image, several references — align them: {divergent}"

    declared = {place: image for place, image in found if place in _DIVERGENT_BY_DESIGN}
    stale = sorted(
        place
        for place in _DIVERGENT_BY_DESIGN
        if place not in declared
        or set(references.get(_repository(declared[place]), {})) in (set(), {declared[place]})
    )
    assert not stale, f"declared divergent but no longer diverging — drop the entry: {stale}"


def test_the_self_host_catalogue_pins_what_production_runs() -> None:
    """``self_host_dependencies.json`` is what a PREBUILT install pins: a compose bump
    that forgets it leaves every new install on the old image (F6). Caddy is the
    installer's own proxy, so its entry is the default ``scripts/install/compose.py``
    renders."""
    catalogue = {
        entry["service"]: entry["reference"]
        for entry in json.loads(
            (ROOT / "scripts/install/self_host_dependencies.json").read_text(encoding="utf-8")
        )
    }
    production = _load("docker-compose.prod.yml")["services"]
    caddy = re.search(
        r"\$\{LIA_CADDY_IMAGE:-([^}]+)\}",
        (ROOT / "scripts/install/compose.py").read_text(encoding="utf-8"),
    )
    assert caddy, "scripts/install/compose.py no longer renders a default Caddy image"

    expected = {
        service: production[service]["image"] for service in catalogue if service in production
    } | {"caddy": caddy.group(1)}
    assert catalogue == expected
