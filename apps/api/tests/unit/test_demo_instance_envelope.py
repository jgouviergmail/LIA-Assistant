"""The demonstrator envelope shares nothing with DEV or PROD.

The application inside is the standard one — that is the design. What makes it
safe to expose is the envelope, so the envelope's properties are pinned here
rather than trusted to a reviewer noticing a stray line in a Compose file.

What must hold:
- its own Compose project, its own internal networks, no external resource;
- no DEV/PROD container name, no normal env file;
- ONLY the edge publishes a host port — a published database port would make
  the isolation decorative;
- the database has no durable volume (tmpfs): a demonstrator that accumulates
  is a demonstrator that leaks;
- the API and the web run read-only, unprivileged, with capabilities dropped;
- the egress proxy is the sole member of the outbound network.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
COMPOSE = REPO_ROOT / "docker-compose.demo-instance.yml"


def _body() -> str:
    return COMPOSE.read_text(encoding="utf-8")


def _service_blocks() -> dict[str, str]:
    body = _body()
    parts = re.split(r"\n  ([a-z][a-z0-9-]*):\n", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_the_envelope_exists_and_names_its_own_project() -> None:
    assert COMPOSE.is_file(), f"missing {COMPOSE}"
    assert re.search(r"^name:\s*lia-demo-instance", _body(), re.M)


def test_no_external_resource_is_joined() -> None:
    # `external: true` would attach a DEV/PROD network or volume — the single
    # line that quietly undoes the whole isolation.
    assert "external: true" not in _body()


@pytest.mark.parametrize(
    "forbidden",
    [
        "lia-api-prod",
        "lia-web-prod",
        "lia-postgres-prod",
        "lia-redis-prod",
        "lia-api-dev",
        "lia-web-dev",
    ],
)
def test_no_dev_or_prod_container_is_referenced(forbidden: str) -> None:
    assert forbidden not in _body()


def test_no_normal_env_file_is_loaded() -> None:
    body = _body()
    assert "env_file: .env\n" not in body
    assert "- .env\n" not in body


def test_the_production_envelope_publishes_no_host_port_at_all() -> None:
    """Reachable through Cloudflare, or not at all.

    This is not only about the data stores. Two protections rest on the
    tunnel being the ONLY way in:

    - the per-address rate limiter keys on ``CF-Connecting-IP``, which is
      trustworthy exactly because Cloudflare writes it and overwrites what a
      visitor sent. Reaching the edge without traversing Cloudflare makes it
      a value the caller chooses, and the limiter stops limiting (measured
      2026-08-07: eight registrations, eight fresh buckets);
    - the edge's allowlist is the surface, and a published port would offer a
      second door to a machine that may host other things.

    The development override publishes a loopback port, deliberately and in
    the file whose name says so.
    """
    import yaml

    compose = yaml.safe_load(_body())
    published = {
        service: spec["ports"]
        for service, spec in compose["services"].items()
        if (spec or {}).get("ports")
    }
    assert not published, (
        f"{published} — the production envelope answers through the tunnel or "
        "not at all; a host port here also un-trusts CF-Connecting-IP"
    )


def test_the_database_has_no_durable_volume() -> None:
    """Nothing the visitors write may outlive the container.

    The check is on what a mount DOES, not on the word `volumes:`. The
    database needs one read-only file — the extension init script shared with
    the development stack, without which the first migration declaring a
    VECTOR column dies. Forbidding the keyword outright made a legitimate,
    non-durable mount look like durable storage.
    """
    postgres = _service_blocks()["demo-instance-postgres"]
    assert "tmpfs:" in postgres
    assert "/var/lib/postgresql/data" in postgres

    # The declared mounts, read as YAML: a regex over the block also matches
    # `${VAR:?message}` in the environment and would fail on a colon.
    import yaml

    compose = yaml.safe_load(_body())
    mounts = compose["services"]["demo-instance-postgres"].get("volumes") or []
    for mount in mounts:
        source, target, *options = str(mount).split(":")
        assert not target.startswith("/var/lib/postgresql"), (
            f"{mount} would survive the nightly reset and accumulate the visitor "
            "data this instance promises to erase"
        )
        assert "ro" in options, (
            f"{mount} is writable — a demonstrator's database container must "
            "keep nothing across a restart"
        )


@pytest.mark.parametrize("service", ["demo-instance-api", "demo-instance-web"])
def test_the_application_runs_read_only_and_unprivileged(service: str) -> None:
    block = _service_blocks()[service]
    assert "read_only: true" in block
    assert "cap_drop: [ALL]" in block
    assert "no-new-privileges:true" in block


def test_every_third_party_image_is_pinned() -> None:
    """A public instance rebuilt tomorrow must be the one reviewed today.

    All eight images were checked for linux/arm64 on 2026-08-07, because the
    production host is a Raspberry Pi — every one publishes it. That check is
    only worth something while the tags stay fixed.
    """
    import yaml

    compose = yaml.safe_load(_body())
    unpinned = []
    for service, spec in compose["services"].items():
        image = (spec or {}).get("image")
        if not image:
            continue  # built from a Dockerfile in this repository
        if ":" not in image or image.rsplit(":", 1)[1] in {"latest", ""}:
            unpinned.append(f"{service}: {image}")

    assert not unpinned, f"{unpinned} — pin the version, the tag is the contract"


def test_the_application_is_the_standard_image() -> None:
    body = _body()
    # The whole point: visitors talk to the real application. A dedicated
    # image would prove nothing about production.
    assert "dockerfile: Dockerfile.prod" in body
    assert "apps/web/Dockerfile.prod" in body


def test_the_internal_networks_are_internal() -> None:
    body = _body()
    for network in (
        "demo-instance-app",
        "demo-instance-data",
        "demo-instance-observability",
        "demo-instance-mail",
        "demo-instance-ingress",
    ):
        block = re.search(rf"\n  {network}:\n(.*?)(?=\n  \w|\Z)", body, re.S)
        assert block and "internal: true" in block.group(1), f"{network} must be internal"


#: The only services allowed a route out, each with the protocol it carries.
#: Three, because three things leave this envelope and no single relay can
#: carry them: a HTTP proxy cannot relay SMTP (a mail library opens a plain
#: TCP connection and would have to know about the proxy — measured
#: 2026-08-07, the verification email never left), and the tunnel carries the
#: visitors themselves. Adding a fourth means widening what a public instance
#: can reach, which is a decision, not an edit.
OUTBOUND_SERVICES = {
    "demo-instance-egress": "HTTPS to the allowlisted provider hosts",
    "demo-instance-smtp": "SMTP to the configured smarthost, and nothing else",
    "demo-instance-tunnel": "the outbound connection Cloudflare answers on",
}


def _non_internal_networks() -> set[str]:
    """Networks from which a member can reach the Internet — and the LAN.

    Recomputed from the file rather than named, because the question "who can
    reach out" is answered by the network's ``internal`` flag, and a new
    non-internal network would otherwise escape the guard entirely.
    """
    import yaml

    compose = yaml.safe_load(_body())
    return {
        name
        for name, spec in (compose.get("networks") or {}).items()
        if not (spec or {}).get("internal", False)
    }


def test_only_the_declared_relays_reach_outbound() -> None:
    routed = _non_internal_networks()
    assert routed, "every network became internal — the tunnel could not connect"

    import yaml

    compose = yaml.safe_load(_body())
    outbound_members = {
        service
        for service, spec in compose["services"].items()
        if routed & set((spec or {}).get("networks") or [])
    }
    assert outbound_members == set(OUTBOUND_SERVICES), (
        "a service gained (or lost) a route to the Internet — every entry in "
        "OUTBOUND_SERVICES states what it carries and why"
    )


def test_the_edge_cannot_reach_the_internet_or_the_local_network() -> None:
    """The most exposed container must not be the widest-reaching one.

    Measured 2026-08-07 inside the edge's own network namespace, while
    `demo-instance-ingress` was still routed: `1.1.1.1:443` connected,
    `<prod-host>:2222` connected — the production Raspberry's SSH — and so
    did the development stack's API on the same machine. Caddy reverse-proxies
    to two containers of the private application network and needs none of it.

    The tunnel keeps the route out, because it is the one service whose job is
    to hold an outbound connection open.
    """
    import yaml

    compose = yaml.safe_load(_body())
    edge_networks = set(compose["services"]["demo-instance-edge"]["networks"])

    assert not (edge_networks & _non_internal_networks()), (
        "the edge joined a routed network: a visitor request terminates there, "
        "and from there the owner's LAN and production host would be one "
        "connect() away"
    )


def test_the_mail_relay_is_reachable_by_the_application_alone() -> None:
    """A relay every container can talk to is a mail cannon with four triggers.

    It holds the smarthost credentials and relays to arbitrary recipients for
    the configured sender domain (measured 2026-08-07: `RCPT 250` to an
    external address). Only the process that sends the verification email has
    any business reaching it.
    """
    import yaml

    compose = yaml.safe_load(_body())
    mail_members = {
        service
        for service, spec in compose["services"].items()
        if "demo-instance-mail" in ((spec or {}).get("networks") or [])
    }

    assert mail_members == {"demo-instance-api", "demo-instance-smtp"}, (
        f"{sorted(mail_members)} share the mail network; the web, the edge and "
        "the proxy have no mail to send"
    )


def test_the_application_itself_never_reaches_outbound() -> None:
    """The property the relays exist to preserve."""
    import yaml

    compose = yaml.safe_load(_body())
    routed = _non_internal_networks()
    for service in ("demo-instance-api", "demo-instance-web"):
        joined = set(compose["services"][service]["networks"]) & routed
        assert not joined, (
            f"{service} joins {sorted(joined)} and would reach the Internet "
            "directly, so the allowlist in front of it would decide nothing"
        )


def test_each_routed_network_carries_exactly_one_container() -> None:
    """Three containers may reach the Internet; none may reach each other.

    They shared one network until 2026-08-07, and the measurement showed what
    that bought: from the egress proxy's namespace, `demo-instance-smtp:25`
    answered. A proxy with a CVE could then send mail as the operator's
    domain. Nothing needs that adjacency.
    """
    import yaml

    compose = yaml.safe_load(_body())
    for network in _non_internal_networks():
        members = sorted(
            service
            for service, spec in compose["services"].items()
            if network in ((spec or {}).get("networks") or [])
        )
        assert len(members) == 1, (
            f"{network} carries {members}: the containers that can reach the "
            "Internet must not be able to reach one another"
        )


def test_the_api_is_told_to_use_the_egress_proxy() -> None:
    api = _service_blocks()["demo-instance-api"]
    assert "HTTPS_PROXY=http://demo-instance-egress:3128" in api


def test_demo_mode_is_declared_in_the_envelope_itself() -> None:
    # Reading the envelope must be enough to know this is a demonstrator.
    assert "DEMO_MODE_ENABLED=true" in _service_blocks()["demo-instance-api"]


def test_the_environment_template_bounds_the_money_and_the_surface() -> None:
    template = (REPO_ROOT / ".env.demo-instance.example").read_text(encoding="utf-8")
    # The financial protection (ADR-216) and the capability decisions
    # (ADR-217) belong to the template, not to folklore.
    assert re.search(r"^INSTANCE_DAILY_BUDGET_EUR=1\.00$", template, re.M)
    assert re.search(r"^IMAGE_GENERATION_ENABLED=false$", template, re.M)
    assert re.search(r"^DEMO_MODE_ENABLED=true$", template, re.M)
    assert re.search(r"^USAGE_LIMITS_ENABLED=true$", template, re.M)


def test_the_template_ships_no_filled_secret() -> None:
    template = (REPO_ROOT / ".env.demo-instance.example").read_text(encoding="utf-8")
    for line in template.splitlines():
        for secret in (
            "SECRET_KEY",
            "FERNET_KEY",
            "OPENAI_API_KEY",
            "SMTP_PASSWORD",
            "POSTGRES_PASSWORD",
        ):
            if line.startswith(f"{secret}="):
                assert line == f"{secret}=", f"{secret} must ship empty, got a value"


def test_the_tunnel_is_the_only_public_way_in() -> None:
    tunnel = _service_blocks()["demo-instance-tunnel"]
    # It dials OUT to Cloudflare: a published port would be a second door,
    # and the whole point is that there is only one.
    assert not re.findall(r'- "?\d+:\d+"?', tunnel)
    assert "demo-instance-ingress" in tunnel
    # Not on the app network: it must reach the edge, never the API directly.
    assert "demo-instance-app" not in tunnel
    assert "cap_drop: [ALL]" in tunnel


def test_the_tunnel_token_is_never_hardcoded() -> None:
    body = _body()
    # A connector token grants inbound traffic to this instance: it lives in
    # the untracked env file, never in a file git follows.
    assert "${DEMO_INSTANCE_TUNNEL_TOKEN" in body
    assert "eyJ" not in body, "a JWT-looking literal must never appear here"


def test_the_tunnel_is_opt_in_so_a_laptop_run_does_not_need_it() -> None:
    tunnel = _service_blocks()["demo-instance-tunnel"]
    assert 'profiles: ["tunnel"]' in tunnel


def test_every_service_declares_a_memory_ceiling() -> None:
    """No container of the envelope may run without a memory limit.

    Two failure modes hang on a missing ``mem_limit``: a runaway demo
    container competes with PRODUCTION for the shared host's memory, and
    cAdvisor reports the absent limit as 0 — which the
    ``ContainerMemoryNearLimit`` expression used to read as +Inf% and fire
    permanently (measured 2026-08-16: 7 unlimited services, ~15 alert mails).
    ``pids_limit`` rides along: a fork bomb is the same class of host risk.
    """
    services = {
        name: block
        for name, block in _service_blocks().items()
        # _service_blocks() also captures network/volume keys at the same
        # indent; a service is the block that declares an image or a build.
        if "image:" in block or "build:" in block
    }
    assert len(services) >= 10, f"service split looks broken: {sorted(services)}"
    for name, block in services.items():
        assert "mem_limit:" in block, f"{name} declares no mem_limit"
        assert "pids_limit:" in block, f"{name} declares no pids_limit"


def test_no_build_context_ships_an_env_file() -> None:
    """A secret must not be able to reach a layer, not merely fail to.

    The web image is built from the repository ROOT (`context: .`), where every
    `.env` of this machine lives. Its Dockerfile copies named paths today, and
    no `.env*` exists in either built image (verified 2026-08-07 with `find /`).
    That is a property of today's Dockerfile: a single `COPY . .` added later
    would ship them all. The exclusion is what makes it structural.
    """
    for context in (REPO_ROOT / ".dockerignore", REPO_ROOT / "apps/api/.dockerignore"):
        assert context.is_file(), f"{context} is missing: its build context ships everything"
        body = context.read_text(encoding="utf-8")
        assert ".env" in body, f"{context} does not exclude environment files"
        assert "example" in body, (
            f"{context} must keep the templates: they are tracked documentation, " "not secrets"
        )
