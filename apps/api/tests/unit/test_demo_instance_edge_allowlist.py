"""The demonstrator edge routes an ALLOWLIST and 404s everything else.

The application already refuses what a visitor must not reach (connector
linking, disabled capabilities, admin endpoints behind a superuser
dependency). This is the layer in front: a path that is not on the list never
reaches the application at all, so a future route lands closed by default
rather than open by accident.

The list is pinned here, in one place, for one reason: "we allowlist routes"
as prose drifts the day someone adds a prefix. A test that reads the actual
Caddyfile cannot.

What must hold:
- every allowed prefix is deliberate and justified in the file itself;
- the paths that would let a visitor link a real Google account, or reach the
  administration, are NOT reachable — checked as classification, not as a
  denylist the edge would have to enumerate;
- the fallback is 404, never a pass-through;
- no access log (a demonstrator's edge has no business keeping visitor paths).
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

CADDYFILE = repo_root_or_skip() / "infrastructure" / "demo-instance" / "Caddyfile"

#: Exactly what the demonstrator exposes. Adding an entry here is a decision
#: that shows up in review; adding one only in the Caddyfile fails.
EXPECTED_ALLOWED = {
    # Getting in and staying in.
    "/api/v1/auth/*",
    # The conversation: SSE stream, history, HITL decisions.
    "/api/v1/agents/*",
    "/api/v1/conversations*",
    "/api/v1/chat/*",
    # The visitor's own account, and what the instance offers.
    "/api/v1/users/*",
    "/api/v1/account/*",
    "/api/v1/usage-limits/me*",
    "/api/v1/usage/*",
    "/api/v1/capabilities",
    "/api/v1/config",
    "/api/v1/system-settings/*",
    "/api/v1/product/*",
    # The product itself. A demonstrator that shows the real assistant must
    # serve the real features: with only the seven prefixes this list used to
    # hold, the personality picker, the timezone list, psyche, journals and
    # skills all answered 404 and the screens came up empty (2026-08-07).
    "/api/v1/personalities*",
    "/api/v1/psyche/*",
    "/api/v1/journals*",
    "/api/v1/memories*",
    "/api/v1/interests*",
    "/api/v1/habits/*",
    "/api/v1/relations/*",
    "/api/v1/open-loops*",
    "/api/v1/briefing/*",
    "/api/v1/heartbeat/*",
    "/api/v1/notifications*",
    "/api/v1/reminders*",
    "/api/v1/scheduled-actions*",
    "/api/v1/skills*",
    "/api/v1/rag-spaces*",
    "/api/v1/attachments*",
    "/api/v1/mcp/*",
    "/api/v1/voice/*",
    "/api/v1/health-metrics/*",
    "/api/v1/image-generation",
    # Liveness only.
    "/health",
    "/ready",
}

#: Paths that must NOT be reachable. Not a denylist the edge enumerates —
#: the edge only knows the allowlist — but the proof that the allowlist does
#: not accidentally cover them.
MUST_NOT_BE_REACHABLE = [
    "/api/v1/connectors/gmail/authorize",
    "/api/v1/connectors/google-calendar/callback",
    "/api/v1/admin/capabilities",
    "/api/v1/admin/system-settings/debug-panel",
    "/api/v1/usage-limits/admin/instance-daily-budget",
    "/api/v1/admin/users",
    "/metrics",
]


def _caddyfile() -> str:
    return CADDYFILE.read_text(encoding="utf-8")


def _allowed_paths() -> set[str]:
    """The path matcher the edge actually declares."""
    match = re.search(r"@allowed\s+path\s+([^\n]+)", _caddyfile())
    assert match, "the edge must declare a single @allowed path matcher"
    return set(match.group(1).split())


def _matches(pattern: str, path: str) -> bool:
    """Caddy path-matching semantics: exact, or prefix when it ends with *."""
    if pattern.endswith("*"):
        return path.startswith(pattern[:-1])
    return path == pattern


def test_the_edge_file_exists() -> None:
    assert CADDYFILE.is_file(), f"missing {CADDYFILE}"


def test_the_allowlist_is_exactly_what_is_expected() -> None:
    assert _allowed_paths() == EXPECTED_ALLOWED


@pytest.mark.parametrize("path", sorted(MUST_NOT_BE_REACHABLE))
def test_sensitive_paths_are_not_covered_by_the_allowlist(path: str) -> None:
    allowed = _allowed_paths()
    covered = [pattern for pattern in allowed if _matches(pattern, path)]
    assert not covered, (
        f"{path} is reachable through {covered} — a visitor could link a real "
        "account or reach the administration of the demonstrator."
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/register",
        "/api/v1/auth/verify-email",
        "/api/v1/agents/chat/stream",
        "/api/v1/conversations",
        "/api/v1/users/me",
        "/api/v1/capabilities",
        "/health",
        "/ready",
    ],
)
def test_the_api_calls_of_the_visitor_journey_stay_reachable(path: str) -> None:
    allowed = _allowed_paths()
    assert any(
        _matches(pattern, path) for pattern in allowed
    ), f"{path} is NOT reachable — the demonstrator journey would break."


@pytest.mark.parametrize("path", ["/", "/fr/demo", "/en/dashboard/chat", "/_next/static/x.js"])
def test_the_localized_web_application_is_served_as_a_whole(path: str) -> None:
    # Pages cannot link an account or flip a switch: their surface IS the
    # public site. Enumerating six locales plus every asset prefix would be a
    # list nobody could keep true.
    assert not path.startswith("/api/"), "web paths must not collide with the API"
    content = _caddyfile()
    assert re.search(
        r"handle\s*\{\s*reverse_proxy\s+demo-instance-web", content
    ), "the edge must end on a web fallback"


def test_any_other_api_path_is_404_not_forwarded() -> None:
    content = _caddyfile()
    # Without this block the web app would receive API calls (a different,
    # confusing failure) and any future /api route would land in it silently.
    assert re.search(
        r"@other_api\s+path\s+/api/\*", content
    ), "the edge must close every API path that is not on the allowlist"
    api_block = content.index("@other_api")
    allow_block = content.index("@allowed")
    web_fallback = content.index("reverse_proxy demo-instance-web")
    # Order is load-bearing in Caddy: allowlist, then the API catch-all, then
    # the web fallback.
    assert allow_block < api_block < web_fallback
    assert content.count("reverse_proxy") == 2, "only the API and the web may be proxied"


def test_the_edge_keeps_no_access_log() -> None:
    # Visitor paths are personal data nobody needs on a throwaway instance.
    assert "log {" not in _caddyfile()


def test_the_admin_endpoint_of_caddy_is_off() -> None:
    assert re.search(r"admin\s+off", _caddyfile()), "Caddy's admin API must be off"


def test_the_edge_terminates_no_tls_and_publishes_no_host_port() -> None:
    """The edge is reachable through Cloudflare, or not at all.

    Two halves of one decision, and both were wrong before being measured:

    - `:443 { tls internal }` served NOTHING. With no site name Caddy has no
      subject to issue a certificate for, and answered `tls alert internal
      error` to every client whatever the SNI (measured 2026-08-06 against a
      real Caddy). The instance would have been unreachable.
    - `ports: 443:443` published the edge to anyone who could reach the host,
      contradicting the "through Cloudflare or not at all" the file claims.
      A local validation publishes a LOOPBACK port through the dev override.

    Encryption between two containers of the same private network buys
    nothing; the tunnel's outbound connection is what is encrypted.
    """
    # Directives only: the file EXPLAINS the removed `tls internal` in prose,
    # and an oracle that reads comments would fail on its own documentation.
    directives = "\n".join(
        line for line in _caddyfile().splitlines() if not line.strip().startswith("#")
    )
    assert "tls internal" not in directives, (
        "the edge must not terminate TLS: with no site name it serves no "
        "certificate at all and every handshake fails"
    )
    assert "auto_https off" in directives, "automatic HTTPS must stay off behind the tunnel"

    compose = (repo_root_or_skip() / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")
    edge_block = compose[
        compose.index("demo-instance-edge:") : compose.index("demo-instance-tunnel:")
    ]
    assert "ports:" not in edge_block, (
        "the production envelope must publish no host port for the edge — "
        "use docker-compose.demo-instance.dev.yml for a local validation"
    )


def test_the_dev_override_binds_to_loopback_only() -> None:
    """A demonstrator's administration must not answer the local network."""
    override = (repo_root_or_skip() / "docker-compose.demo-instance.dev.yml").read_text(
        encoding="utf-8"
    )
    published = [
        line.strip().strip("-").strip().strip('"')
        for line in override.splitlines()
        if ":" in line and line.strip().startswith('- "')
    ]
    assert published, "the dev override must publish something, or it is pointless"
    for mapping in published:
        assert mapping.startswith("127.0.0.1:"), (
            f"{mapping} publishes beyond loopback: without the 127.0.0.1 prefix "
            "Docker binds 0.0.0.0 and the demonstrator answers the whole LAN"
        )


def test_no_profiled_service_makes_a_variable_required() -> None:
    """A service nobody starts must not be able to stop the start.

    Compose interpolates the WHOLE file before it filters profiles, so a
    `${VAR:?message}` inside a profiled service fails `up -d` even when that
    service is not part of the run. Measured 2026-08-06 on the very first
    real start: the tunnel token — a production secret, absent from the dev
    env file by design — blocked the local validation entirely.

    Requirements belong to the task that needs them, where the message can
    say what to do about it.
    """
    import yaml

    compose = yaml.safe_load(
        (repo_root_or_skip() / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")
    )
    offenders = []
    for name, service in (compose.get("services") or {}).items():
        if not service.get("profiles"):
            continue
        if ":?" in yaml.safe_dump(service):
            offenders.append(name)
    assert not offenders, (
        f"profiled service(s) {offenders} declare a REQUIRED variable — that "
        "blocks every start, including runs without their profile"
    )


def test_the_api_and_the_database_agree_on_who_connects() -> None:
    """The standard image's entrypoint reads POSTGRES_*, never DATABASE_URL.

    Running the STANDARD image means honouring its contract: `pg_isready` and
    the seeding `psql` calls take the host, user, database and password from
    four environment variables. Setting only `DATABASE_URL` left the
    entrypoint waiting on a host named `postgres` that exists nowhere in this
    envelope — two minutes of "PostgreSQL is unavailable", then an unhealthy
    container (measured 2026-08-06 on the first real start).

    The two services must therefore agree, and the password must have one
    source: the same interpolated variable both read.
    """
    import yaml

    compose = yaml.safe_load(
        (repo_root_or_skip() / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")
    )

    def _env(service: str) -> dict[str, str]:
        raw = compose["services"][service].get("environment") or []
        pairs = (item.split("=", 1) for item in raw if "=" in item)
        return dict(pairs)

    api, database = _env("demo-instance-api"), _env("demo-instance-postgres")

    assert (
        api["POSTGRES_HOST"] in compose["services"]
    ), f"the API waits on {api['POSTGRES_HOST']}, which is not a service of this envelope"
    for key in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"):
        assert api[key] == database[key], (
            f"{key} differs between the API and its database — the entrypoint "
            "would wait forever on credentials nobody granted"
        )
