"""Compose layer selection and override rendering contract (B04/B05/B15).

- the base+install prefix is EXACTLY the two ``-f`` layers, each argv
  element distinct — never a joined filename;
- the generated override always carries the seed-bundle digest, and only
  the fresh-start candidate arms ``APPLY_SEEDS=true``;
- LAN republises the web port with a Compose ``!override`` list; proxy adds
  no ports; only Caddy exposure adds the ``caddy`` service (80/443, named
  volumes, read-only generated Caddyfile);
- observability/skill layers appear only when selected;
- prebuilt appends the digest-only image lock and ``--no-build``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.install.compose import (
    build_invocation,
    render_caddyfile,
    render_install_override,
    up_suffix,
)
from scripts.install.model import Exposure, InstallMode, PublicAnswers

DIGEST = "a" * 64


class _OverrideLoader(yaml.SafeLoader):
    """Understands the Compose `!override` tag (Compose >= 2.24.4)."""


_OverrideLoader.add_constructor(
    "!override", lambda loader, node: loader.construct_sequence(node)
)


def _public(
    exposure: Exposure = Exposure.LAN,
    *,
    mode: InstallMode = InstallMode.LOCAL,
    observability: bool = False,
    skill_sandbox: bool = False,
) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=mode,
        exposure=exposure,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=observability,
        skill_sandbox=skill_sandbox,
        server_host="192.168.1.50" if exposure is Exposure.LAN else None,
        web_domain=None if exposure is Exposure.LAN else "lia.example.org",
        api_domain=None if exposure is Exposure.LAN else "api.example.org",
        caddy_email="acme@example.org" if exposure is Exposure.CADDY else None,
        manifest_path=None,
    )


def _render(public: PublicAnswers, *, seed_intent: bool = True, **kwargs: object) -> dict:
    text = render_install_override(
        public, seed_intent=seed_intent, seed_bundle_sha256=DIGEST, **kwargs
    )
    return yaml.load(text, Loader=_OverrideLoader)


def _api_env(parsed: dict) -> dict[str, str]:
    entries = parsed["services"]["api"]["environment"]
    return dict(entry.split("=", 1) for entry in entries)


def test_base_install_prefix_is_exactly_two_distinct_layers() -> None:
    invocation = build_invocation(_public(), root=Path("."))
    prefix = invocation.prefix()
    assert prefix[:2] == ["docker", "compose"]
    tail = prefix[2:]
    assert tail == [
        "-f",
        "docker-compose.prod.yml",
        "-f",
        "docker-compose.install.yml",
    ]


def test_override_always_carries_the_digest_and_seed_intent_gates_apply() -> None:
    armed = _api_env(_render(_public(), seed_intent=True))
    disarmed = _api_env(_render(_public(), seed_intent=False))
    assert armed["APPLY_SEEDS"] == "true"
    assert disarmed["APPLY_SEEDS"] == "false"
    assert armed["SEED_BUNDLE_SHA256"] == DIGEST
    assert disarmed["SEED_BUNDLE_SHA256"] == DIGEST


def test_lan_overrides_the_web_port_list() -> None:
    text = render_install_override(
        _public(Exposure.LAN), seed_intent=True, seed_bundle_sha256=DIGEST
    )
    assert "!override" in text
    parsed = yaml.load(text, Loader=_OverrideLoader)
    assert parsed["services"]["web"]["ports"] == ["3000:3000"]
    assert "caddy" not in parsed["services"]
    # The API port stays loopback-only (base file): no api ports override.
    assert "ports" not in parsed["services"]["api"]


def test_proxy_adds_no_ports_and_no_caddy() -> None:
    parsed = _render(_public(Exposure.PROXY))
    assert "ports" not in parsed["services"].get("web", {})
    assert "caddy" not in parsed["services"]


def test_caddy_exposure_owns_the_caddy_service_and_volumes() -> None:
    parsed = _render(_public(Exposure.CADDY))
    caddy = parsed["services"]["caddy"]
    assert caddy["image"] == "${LIA_CADDY_IMAGE:-caddy:2-alpine}"
    assert set(caddy["ports"]) == {"80:80", "443:443"}
    volumes = caddy["volumes"]
    assert "./infrastructure/caddy/Caddyfile:/etc/caddy/Caddyfile:ro" in volumes
    assert any(v.startswith("caddy_data:") for v in volumes)
    assert any(v.startswith("caddy_config:") for v in volumes)
    assert set(parsed["volumes"]) == {"caddy_data", "caddy_config"}


def test_sandbox_prebuilt_pins_the_sandbox_image_to_the_api_digest() -> None:
    api_reference = f"ghcr.io/o/r/api@sha256:{DIGEST}"
    env = _api_env(
        _render(
            _public(skill_sandbox=True, mode=InstallMode.PREBUILT),
            sandbox_api_image=api_reference,
        )
    )
    assert env["SKILLS_SCRIPT_SANDBOX_IMAGE"] == api_reference


def test_layer_selection_follows_the_choices() -> None:
    plain = build_invocation(_public(), root=Path("."))
    assert plain.profiles == ()
    assert [p.name for p in plain.files] == [
        "docker-compose.prod.yml",
        "docker-compose.install.yml",
    ]

    rich = build_invocation(
        _public(observability=True, skill_sandbox=True), root=Path(".")
    )
    assert rich.profiles == ("observability",)
    assert [p.name for p in rich.files] == [
        "docker-compose.prod.yml",
        "docker-compose.install.yml",
        "docker-compose.skill-sandbox.yml",
    ]


def test_prebuilt_appends_the_image_lock_layer_and_no_build() -> None:
    prebuilt = build_invocation(
        _public(mode=InstallMode.PREBUILT), root=Path(".")
    )
    assert [p.name for p in prebuilt.files] == [
        "docker-compose.prod.yml",
        "docker-compose.install.yml",
        "docker-compose.images.yml",
    ]
    assert "--no-build" in up_suffix(prebuilt)
    assert "--no-build" not in up_suffix(build_invocation(_public(), root=Path(".")))


def test_up_suffix_never_joins_arguments() -> None:
    for suffix in (
        up_suffix(build_invocation(_public(), root=Path("."))),
        up_suffix(build_invocation(_public(mode=InstallMode.PREBUILT), root=Path("."))),
    ):
        assert all(" " not in arg for arg in suffix), suffix


def test_caddyfile_renders_both_vhosts_and_acme_email() -> None:
    rendered = render_caddyfile(_public(Exposure.CADDY))
    assert "lia.example.org" in rendered
    assert "api.example.org" in rendered
    assert "acme@example.org" in rendered
    assert "reverse_proxy web:3000" in rendered
    assert "reverse_proxy api:8000" in rendered


def test_caddyfile_requires_the_caddy_exposure() -> None:
    with pytest.raises(ValueError):
        render_caddyfile(_public(Exposure.LAN))


def test_locked_services_match_the_dependency_catalogue_and_base_file() -> None:
    import json

    from scripts.install.compose import locked_services
    from scripts.install.tests.conftest import REPO_ROOT

    catalogue = {
        entry["service"]
        for entry in json.loads(
            (REPO_ROOT / "scripts/release/self_host_dependencies.json").read_text(
                encoding="utf-8"
            )
        )
    }
    full = locked_services(
        _public(Exposure.CADDY, mode=InstallMode.PREBUILT, observability=True)
    )
    assert set(full) == catalogue | {"api", "web"}
    lan = locked_services(_public(Exposure.LAN, mode=InstallMode.PREBUILT))
    assert "caddy" not in lan
    assert not any(s in lan for s in ("grafana", "prometheus"))
