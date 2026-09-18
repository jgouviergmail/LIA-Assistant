"""The proxy ruleset is rendered by LIA, from the live runs, and nothing else.

Two golden nets: the EMPTY rendering is byte-for-byte the bootstrap file the
proxy starts on (one declaration of the proxy's shape, kept where a shell can
copy it), and a two-run rendering is frozen so a change to the shape is a
reviewed diff, never a silent drift.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
import yaml

from src.domains.agents.python_sandbox.egress.registry import LiveRun, RunCredential
from src.domains.agents.python_sandbox.egress.ruleset import (
    RulesetConfig,
    remove_run_secrets,
    render_ruleset,
    write_run_secrets,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
HERE = Path(__file__).parent
BOOTSTRAP = ROOT / "infrastructure/sandbox-egress/proxy.bootstrap.yaml"
GOLDEN = HERE / "golden_ruleset.yaml"

CONFIG = RulesetConfig(max_body_bytes=1_048_576)


def _runs() -> list[LiveRun]:
    return [
        LiveRun(
            run_id="run-a",
            user_id="user-a",
            hosts=("api.search.brave.com", "api.openweathermap.org", "example.org"),
            credentials=(
                RunCredential(
                    connector="brave_search",
                    host="api.search.brave.com",
                    token="sbx_run-a_brave",
                    auth_method="header",
                    auth_name="X-Subscription-Token",
                    secret_path="/etc/lia-egress/config/secrets/run-a/brave_search.key",
                ),
                RunCredential(
                    connector="openweathermap",
                    host="api.openweathermap.org",
                    token="sbx_run-a_owm",
                    auth_method="query",
                    auth_name="appid",
                    secret_path="/etc/lia-egress/config/secrets/run-a/openweathermap.key",
                ),
            ),
        ),
        LiveRun(
            run_id="run-b",
            user_id="user-b",
            hosts=("api.perplexity.ai", "example.org"),
            credentials=(
                RunCredential(
                    connector="perplexity",
                    host="api.perplexity.ai",
                    token="sbx_run-b_pplx",
                    auth_method="header",
                    auth_name="Authorization",
                    secret_path="/etc/lia-egress/config/secrets/run-b/perplexity.key",
                ),
            ),
        ),
    ]


def _bootstrap_body() -> str:
    """The bootstrap file minus its comment header (prose for the reader)."""
    lines = [
        line
        for line in BOOTSTRAP.read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    return "\n".join(lines).lstrip("\n") + "\n"


class TestGoldenRenderings:
    def test_no_run_renders_exactly_the_bootstrap_file(self) -> None:
        assert render_ruleset([], CONFIG) == _bootstrap_body()

    def test_two_runs_render_the_frozen_golden(self) -> None:
        assert render_ruleset(_runs(), CONFIG) == GOLDEN.read_text(encoding="utf-8")

    def test_the_rendering_parses_and_names_every_host_once(self) -> None:
        doc = yaml.safe_load(render_ruleset(_runs(), CONFIG))
        allowlist = doc["transforms"][0]["config"]["domains"]
        assert allowlist == sorted(set(allowlist))
        assert set(allowlist) == {
            "api.search.brave.com",
            "api.openweathermap.org",
            "example.org",
            "api.perplexity.ai",
        }
        secrets = doc["transforms"][1]["config"]["secrets"]
        assert [s["replace"]["proxy_value"] for s in secrets] == [
            "sbx_run-a_brave",
            "sbx_run-a_owm",
            "sbx_run-b_pplx",
        ]
        # Every rule binds its token to ITS host alone, and a query credential
        # scans the query string where a header credential scans its header.
        assert secrets[0]["rules"] == [{"host": "api.search.brave.com"}]
        assert secrets[0]["replace"]["match_headers"] == ["X-Subscription-Token"]
        assert secrets[0]["replace"]["match_query"] is False
        assert secrets[1]["replace"]["match_headers"] == []
        assert secrets[1]["replace"]["match_query"] is True
        # `require` stays off: the sandbox never holds a real key, so nothing
        # is protected by rejecting a token-less request — while a second
        # run on the same host with no credential WOULD be refused by it.
        assert all(s["replace"]["require"] is False for s in secrets)

    def test_a_real_key_never_reaches_the_rendering(self) -> None:
        rendered = render_ruleset(_runs(), CONFIG)
        for secret in yaml.safe_load(rendered)["transforms"][1]["config"]["secrets"]:
            assert secret["source"]["type"] == "file"
            assert secret["source"]["path"].startswith("/etc/lia-egress/config/secrets/")


class TestSecretFiles:
    def test_written_private_and_removed_whole(self, tmp_path: Path) -> None:
        paths = write_run_secrets(tmp_path, "run-a", {"brave_search": "REAL-KEY"})
        assert paths == {"brave_search": tmp_path / "secrets" / "run-a" / "brave_search.key"}
        target = paths["brave_search"]
        assert target.read_text(encoding="utf-8") == "REAL-KEY"
        if os.name != "nt":
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
            assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
        remove_run_secrets(tmp_path, "run-a")
        assert not target.parent.exists()

    def test_removing_an_absent_run_is_silent(self, tmp_path: Path) -> None:
        remove_run_secrets(tmp_path, "never-registered")


class TestTheDenyListIsComplete:
    """A declared host may RESOLVE anywhere (rebinding, a name the operator
    trusts pointing inward): the proxy refuses the connect by CIDR, so every
    address that reaches something of ours must be in the list — including
    ``0.0.0.0``, which Linux routes to loopback, and the NAT64 prefix that maps
    an IPv4 address into IPv6 (measured 2026-09-18: the allowlist refused
    ``CONNECT 0.0.0.0``, but a permitted NAME resolving there would pass it)."""

    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "0.0.0.0",
            "10.1.2.3",
            "172.19.0.2",
            "192.168.0.29",
            "169.254.169.254",
            "100.64.1.1",
            "198.18.0.1",
            "::1",
            "::",
            "fe80::1",
            "fd00::1",
            "::ffff:10.0.0.1",
            "64:ff9b::a00:1",
        ],
    )
    def test_every_inward_address_is_denied(self, address: str) -> None:
        import ipaddress

        from src.domains.agents.python_sandbox.egress.ruleset import DENY_CIDRS

        ip = ipaddress.ip_address(address)
        assert any(
            ip in ipaddress.ip_network(cidr) for cidr in DENY_CIDRS
        ), f"{address} would be connected to"

    def test_a_public_address_is_not_denied(self) -> None:
        import ipaddress

        from src.domains.agents.python_sandbox.egress.ruleset import DENY_CIDRS

        for address in ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"):
            ip = ipaddress.ip_address(address)
            assert not any(ip in ipaddress.ip_network(cidr) for cidr in DENY_CIDRS), address
