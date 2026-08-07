"""The template an operator copies must produce an instance that works.

``.env.demo-instance.example`` is the ONLY instruction a production operator
gets. Following it on 2026-08-07 would have produced an instance that:

- cannot send the verification email, because the template names ``SMTP_HOST``,
  ``SMTP_USER`` and ``SMTP_PASSWORD``, which nothing in this codebase reads —
  the mail chain is ``ALERTMANAGER_SMTP_SMARTHOST`` plus the relay's own
  ``DEMO_INSTANCE_SMTP_SMARTHOST`` and ``DEMO_INSTANCE_MAIL_DOMAIN``;
- sends a DEAD verification link, because ``FRONTEND_URL`` — the setting that
  builds it (``auth/service.py``) — is absent from the template entirely. The
  trap was already paid once: the link read ``https://localhost:/verify-email``;
- calls a provider it has no key for, because the template offers
  ``OPENAI_API_KEY`` while ``DEMO_INSTANCE_LLM_PROVIDER`` is ``deepseek``;
- does not start at all under ``task demo:up:tunnel``, the only path that puts
  it on the Internet: Compose interpolation reached ``${DEMO_INSTANCE_SMTP_
  SMARTHOST:?…}`` and stopped (measured).

Twenty-three keys the real files carry were missing from the template, and
five keys the template carried were read by nothing.

These guards RECALCULATE the requirement instead of listing today's keys:
what the Compose files interpolate IS what the template must declare.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
TEMPLATE = ROOT / ".env.demo-instance.example"
COMPOSE_FILES = (
    ROOT / "docker-compose.demo-instance.yml",
    ROOT / "docker-compose.demo-instance.dev.yml",
)

#: Interpolated names the template must NOT declare, with the reason.
#: `DEMO_INSTANCE_ENV_FILE` selects which env file to read: declaring it
#: inside that file would be circular.
NOT_TEMPLATE_KEYS: dict[str, str] = {
    "DEMO_INSTANCE_ENV_FILE": "chooses the env file; declaring it inside one is circular",
}


def _template_path(suffix: str = "") -> Path:
    """The demonstrator template for this shape (``""`` dev, ``".prod"``)."""
    return ROOT / f".env.demo-instance{suffix}.example"


def _declared_keys(path: Path | None = None) -> dict[str, str]:
    """Every ``KEY=value`` the given template declares."""
    declared: dict[str, str] = {}
    for line in (path or TEMPLATE).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        declared[key.strip()] = value.strip()
    return declared


def _interpolated_keys() -> set[str]:
    """Variables the Compose files expect the ENVIRONMENT to carry.

    Only those without a Compose default. ``${VAR:-}`` and ``${VAR:-8090}``
    declare their own fallback, so the envelope starts without them — the
    tunnel token and the loopback ports are exactly that, and demanding them
    in every template would force a production file to carry dev-only ports
    and a dev file to carry a token it never uses.

    ``${VAR:?message}`` and bare ``${VAR}`` have no fallback: their absence
    stops the start-up dead, before any container runs (measured 2026-08-07
    with DEMO_INSTANCE_SMTP_SMARTHOST).
    """
    required: set[str] = set()
    for path in COMPOSE_FILES:
        body = path.read_text(encoding="utf-8")
        for name, modifier in re.findall(r"\$\{([A-Z0-9_]+)(:[-?][^}]*)?\}", body):
            if modifier.startswith(":-"):
                continue
            required.add(name)
    return required


class TestTheGuardReadsSomething:
    def test_the_template_parses(self) -> None:
        declared = _declared_keys()

        assert declared.get("DEMO_MODE_ENABLED") == "true"
        assert len(declared) > 20, f"only parsed {len(declared)} keys"

    def test_the_compose_files_interpolate_something(self) -> None:
        """A parser matching nothing would make the agreement test vacuous."""
        required = _interpolated_keys()

        assert required, "no required variable parsed from the Compose files"
        # The database password is the canonical `${VAR:?}` — no default, and
        # the envelope refuses to render without it.
        assert "DEMO_INSTANCE_POSTGRES_PASSWORD" in required


class TestTheEnvelopeAndTheTemplateAgree:
    def test_every_variable_compose_needs_is_in_the_template(self) -> None:
        missing = sorted(_interpolated_keys() - set(_declared_keys()) - set(NOT_TEMPLATE_KEYS))

        assert not missing, (
            f"{missing} are interpolated by the demonstrator's Compose files but "
            "absent from the template. A required one stops the start-up dead "
            "(measured 2026-08-07: DEMO_INSTANCE_SMTP_SMARTHOST made "
            "`task demo:up:tunnel` fail before any container ran)."
        )


class TestTheMailChainIsTheOneTheCodeReads:
    def test_the_template_names_the_settings_the_application_reads(self) -> None:
        declared = _declared_keys()

        for key in (
            "ALERTMANAGER_SMTP_SMARTHOST",
            "APPLICATION_SMTP_FROM",
            "DEMO_INSTANCE_SMTP_SMARTHOST",
            "DEMO_INSTANCE_MAIL_DOMAIN",
        ):
            assert key in declared, (
                f"{key} is how mail actually leaves this envelope; without it "
                "the verification email — the step that ACTIVATES a visitor — "
                "never goes out"
            )

    @pytest.mark.parametrize(
        "phantom", ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_PORT", "SMTP_FROM"]
    )
    def test_it_does_not_name_settings_nothing_reads(self, phantom: str) -> None:
        assert phantom not in _declared_keys(), (
            f"{phantom} is read by nothing in this codebase. An operator who "
            "fills it in gets an instance that cannot send mail and no error "
            "saying why."
        )


class TestTheApplicationTalksToTheRelayAndTheRelayToTheProvider:
    """Two smarthosts, and swapping them silently kills the signup journey.

    ``ALERTMANAGER_SMTP_SMARTHOST`` is what the APPLICATION opens a socket to;
    ``DEMO_INSTANCE_SMTP_SMARTHOST`` is what the RELAY forwards to. The
    application sits on no outbound network, so pointing it straight at the
    provider means the verification email — the step that ACTIVATES a visitor
    — can never leave, and the failure is a log line nobody reads.

    Found on 2026-08-07 in the real production env file, which named the
    provider on both sides.
    """

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_application_side_names_the_relay_service(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))
        app_side = declared["ALERTMANAGER_SMTP_SMARTHOST"]

        assert app_side.startswith("demo-instance-smtp"), (
            f"the application must hand its mail to the relay on the private "
            f"network, not to {app_side!r}: it has no route to the Internet, so "
            "the verification email would never leave"
        )

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_relay_side_does_not_name_the_relay(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))
        relay_side = declared["DEMO_INSTANCE_SMTP_SMARTHOST"]

        assert not relay_side.startswith("demo-instance-smtp"), (
            "the relay would forward to itself: DEMO_INSTANCE_SMTP_SMARTHOST is "
            "the real provider, ALERTMANAGER_SMTP_SMARTHOST is the relay"
        )

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_relay_credentials_ship_empty(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))

        for key in ("ALERTMANAGER_SMTP_AUTH_USERNAME", "ALERTMANAGER_SMTP_AUTH_PASSWORD"):
            assert declared[key] == "", (
                f"{key} carries a value in a committed template; the smarthost "
                "credentials belong to the relay and to nobody else"
            )


class TestTheProductionTemplateExists:
    """An operator deploying for real copies THIS file, not the dev one."""

    def test_it_ships(self) -> None:
        assert _template_path(".prod").is_file(), (
            ".env.demo-instance.prod.example is what an operator copies to "
            ".env.demo-instance.prod; without it the production shape is folklore"
        )

    def test_it_declares_the_tunnel_token_the_public_path_needs(self) -> None:
        declared = _declared_keys(_template_path(".prod"))

        assert "DEMO_INSTANCE_TUNNEL_TOKEN" in declared, (
            "`task demo:prod:up` is the only path that puts the instance on the "
            "Internet, and the tunnel is what it needs"
        )
        assert declared["DEMO_INSTANCE_TUNNEL_TOKEN"] == ""

    def test_it_publishes_no_local_port(self) -> None:
        """Production answers through the tunnel or not at all."""
        declared = _declared_keys(_template_path(".prod"))

        for dev_only in ("DEMO_INSTANCE_EDGE_PORT", "DEMO_INSTANCE_API_PORT"):
            assert dev_only not in declared, (
                f"{dev_only} belongs to the development override; declaring it "
                "in the production template invites publishing a host port, "
                "which un-trusts CF-Connecting-IP as well"
            )

    def test_its_urls_are_not_localhost(self) -> None:
        declared = _declared_keys(_template_path(".prod"))

        for key in ("APP_URL_SERVER", "FRONTEND_URL"):
            assert (
                "localhost" not in declared[key]
            ), f"{key} builds links a visitor clicks; localhost is the dev shape"


class TestTheThreeUrlsMoveTogether:
    """One address, three variables. They were desynchronised once already."""

    def test_the_template_declares_the_url_that_builds_email_links(self) -> None:
        declared = _declared_keys()

        assert "FRONTEND_URL" in declared, (
            "auth/service.py builds the verification link from FRONTEND_URL, "
            "not from APP_URL_SERVER; a template that omits it ships a dead link"
        )
        assert "APP_URL_SERVER" in declared

    def test_they_describe_the_same_origin(self) -> None:
        declared = _declared_keys()

        assert declared["FRONTEND_URL"] == declared["APP_URL_SERVER"], (
            "the demonstrator is served same-origin by its edge: a template "
            "whose two URLs differ teaches an operator that they may"
        )

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_session_cookie_is_bound_to_that_host_and_no_parent(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))
        cookie_domain = declared["SESSION_COOKIE_DOMAIN"]
        origin = declared["APP_URL_SERVER"]

        if "localhost" in origin:
            # An empty domain gives a HOST-ONLY cookie, which is what
            # `localhost` needs: naming a domain there makes the browser drop
            # it, and the session never survives the redirect.
            assert cookie_domain == "", (
                "a local validation must leave the cookie domain empty; "
                f"{cookie_domain!r} would be dropped by the browser"
            )
            return

        assert cookie_domain, "an empty cookie domain leaves the scope implicit"
        assert not cookie_domain.startswith("."), (
            "a leading dot shares the cookie with every sibling host, which is "
            "how a throwaway demonstrator would hand sessions to the main "
            "instance and receive its own"
        )
        assert origin.endswith(
            cookie_domain
        ), "the cookie domain must be the host the instance is served on"

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_two_urls_describe_the_same_origin(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))

        assert declared["FRONTEND_URL"] == declared["APP_URL_SERVER"], (
            "the demonstrator is served same-origin by its edge: a template "
            "whose two URLs differ teaches an operator that they may"
        )

    def test_the_local_template_points_at_the_edge_port_it_publishes(self) -> None:
        """The trap already paid: a link nobody could click."""
        declared = _declared_keys(_template_path(""))
        port = declared["DEMO_INSTANCE_EDGE_PORT"]

        assert declared["FRONTEND_URL"].endswith(f":{port}"), (
            f"FRONTEND_URL builds the verification link and must name the port "
            f"the edge actually publishes ({port})"
        )


class TestTheConnectionBudgetFitsTheDemonstratorsOwnDatabase:
    """A budget computed against a ceiling that does not exist protects nothing.

    Measured 2026-08-07: the demonstrator booted in development and died on the
    Raspberry with ``ConnectionBudgetError: worst-case burst 288 exceeds usable
    195``. Two faults, and each alone was enough:

    - the template declared none of these settings, so the code defaults applied
      (4 workers x (30+30) + 4x8 + 4x4 = 288);
    - the reference ceiling was wrong. The demonstrator's database is a stock
      ``pgvector/pgvector:pg16``, whose ``max_connections`` is 100, not the 200
      the setting claimed (verified with ``show max_connections``).

    The check only RAISES in production, which is why development never
    flagged it. So the numbers are recomputed here, with the formula the
    application uses, against the ceiling the envelope actually starts.
    """

    #: What the envelope's PostgreSQL really offers. Stock image, no `command:`
    #: override, so this is the server default — not a setting we may choose.
    STOCK_POSTGRES_MAX_CONNECTIONS = 100

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_declared_ceiling_matches_the_database_that_is_started(self, template: str) -> None:
        declared = _declared_keys(_template_path(template))

        assert int(declared["DATABASE_MAX_CONNECTIONS"]) <= self.STOCK_POSTGRES_MAX_CONNECTIONS, (
            "the envelope starts a stock pgvector image whose max_connections is "
            f"{self.STOCK_POSTGRES_MAX_CONNECTIONS}; a budget computed against a "
            "higher number is arithmetic about a server that does not exist"
        )

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_worst_case_burst_fits(self, template: str) -> None:
        from src.core.constants import (
            LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE_DEFAULT,
            LANGGRAPH_STORE_POOL_MAX_SIZE_DEFAULT,
        )

        declared = _declared_keys(_template_path(template))
        workers = int(declared["WEB_CONCURRENCY"])
        per_worker = int(declared["DATABASE_POOL_SIZE"]) + int(declared["DATABASE_MAX_OVERFLOW"])
        checkpointer = LANGGRAPH_CHECKPOINT_POOL_MAX_SIZE_DEFAULT
        store = LANGGRAPH_STORE_POOL_MAX_SIZE_DEFAULT

        burst = workers * (per_worker + checkpointer + store)
        usable = int(declared["DATABASE_MAX_CONNECTIONS"]) - 5  # database_reserved_connections

        assert burst <= usable, (
            f"worst-case burst {burst} exceeds usable {usable}: the instance "
            "would refuse to boot in production, exactly as it did on the "
            "Raspberry on 2026-08-07"
        )

    @pytest.mark.parametrize("template", ["", ".prod"])
    def test_the_envelope_does_not_raise_the_database_ceiling_behind_our_back(
        self, template: str
    ) -> None:
        """If someone gives Postgres more connections, say so here too."""
        envelope = (ROOT / "docker-compose.demo-instance.yml").read_text(encoding="utf-8")
        postgres = envelope[envelope.index("demo-instance-postgres:") :]

        assert "max_connections" not in postgres.split("demo-instance-redis:")[0], (
            "the envelope now tunes max_connections — update "
            "STOCK_POSTGRES_MAX_CONNECTIONS and the templates together"
        )
