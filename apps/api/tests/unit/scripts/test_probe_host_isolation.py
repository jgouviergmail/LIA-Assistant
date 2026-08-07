"""The probe must look where the host actually is.

Its first version read the GATEWAY column of ``/proc/net/route`` and reported
"no gateway, nothing to reach" — on a container that could reach its host. A
Docker network marked ``internal`` installs no default route at all, yet the
bridge address sits in the subnet and answers as a direct neighbour.

Measured both ways on 2026-08-07:

- host silent  -> ``host isolation OK: 4 host address(es) probed``, exit 0;
- host listening on 0.0.0.0:2375, probe on an ``--internal`` network ->
  ``HOST REACHABLE ... 172.29.0.1:2375``, exit 1.

A probe that cannot fail is a green light nobody verified, so the discovery is
pinned here against real routing-table content.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
PROBE = ROOT / "apps/api/scripts/ops/probe_host_isolation.py"


def _module() -> Any:
    """Load the probe as a module: it is a standalone script, not a package."""
    spec = importlib.util.spec_from_file_location("probe_host_isolation", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _route_table(rows: list[str]) -> str:
    header = (
        "Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask" "\t\tMTU\tWindow\tIRTT"
    )
    return "\n".join([header, *rows]) + "\n"


#: 172.21.0.0/16, on-link, no gateway — what an `internal` network looks like.
_INTERNAL_ROUTE = "eth0\t000015AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0"
#: 172.22.0.0/16 with a default route through 172.22.0.1 — a routed network.
_ROUTED_DEFAULT = "eth1\t00000000\t010016AC\t0003\t0\t0\t0\t00000000\t0\t0\t0"


class TestItFindsTheHostOnAnInternalNetwork:
    def test_an_on_link_subnet_yields_its_first_usable_address(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _module()
        route = tmp_path / "route"
        route.write_text(_route_table([_INTERNAL_ROUTE]), encoding="ascii")
        monkeypatch.setattr(module, "Path", lambda _: route)

        # 172.21.0.0/16 -> the bridge, and therefore the host, is 172.21.0.1.
        assert module._host_addresses() == ["172.21.0.1"]

    def test_a_default_gateway_is_found_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _module()
        route = tmp_path / "route"
        route.write_text(_route_table([_ROUTED_DEFAULT]), encoding="ascii")
        monkeypatch.setattr(module, "Path", lambda _: route)

        assert module._host_addresses() == ["172.22.0.1"]

    def test_both_kinds_are_collected_without_duplicates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module = _module()
        route = tmp_path / "route"
        route.write_text(
            _route_table([_INTERNAL_ROUTE, _ROUTED_DEFAULT, _INTERNAL_ROUTE]), encoding="ascii"
        )
        monkeypatch.setattr(module, "Path", lambda _: route)

        assert module._host_addresses() == ["172.21.0.1", "172.22.0.1"]


class TestAnEmptyAnswerIsRefusedNotCelebrated:
    def test_no_address_exits_non_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Indistinguishable from a probe looking in the wrong place — as it did."""
        module = _module()
        route = tmp_path / "route"
        route.write_text(_route_table([]), encoding="ascii")
        monkeypatch.setattr(module, "Path", lambda _: route)

        assert module.main() == 1
        assert "no host address discovered" in capsys.readouterr().out

    def test_an_unreadable_routing_table_exits_non_zero(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _module()

        def _explode(_: object) -> object:
            raise OSError("procfs not mounted")

        monkeypatch.setattr(module, "Path", _explode)

        assert module.main() == 1
        assert "refusing to report success" in capsys.readouterr().out


class TestTheVerdictFollowsTheMeasurement:
    def test_an_answering_port_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _module()
        route = tmp_path / "route"
        route.write_text(_route_table([_INTERNAL_ROUTE]), encoding="ascii")
        monkeypatch.setattr(module, "Path", lambda _: route)
        monkeypatch.setattr(module, "_reachable", lambda host, port: port == 22)

        assert module.main() == 1
        output = capsys.readouterr().out
        assert "HOST REACHABLE" in output
        assert "172.21.0.1:22" in output
        # The message must say what to do, not only that something is wrong.
        assert "harden-demo-host.sh" in output

    def test_silence_everywhere_passes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        module = _module()
        route = tmp_path / "route"
        route.write_text(_route_table([_INTERNAL_ROUTE]), encoding="ascii")
        monkeypatch.setattr(module, "Path", lambda _: route)
        monkeypatch.setattr(module, "_reachable", lambda host, port: False)

        assert module.main() == 0
        assert "host isolation OK" in capsys.readouterr().out

    def test_it_probes_the_ports_that_would_matter(self) -> None:
        """A port list that omits remote shell would pass a compromised host."""
        ports = {port for port, _ in _module()._PORTS}

        assert {22, 2222} & ports, "remote shell is the prize on the production host"
        assert {5432, 6379} & ports, "the databases a sibling stack publishes"


class TestTheDeploymentCanInstallTheCountermeasure:
    def test_the_hardening_script_ships_and_is_idempotent(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        # DOCKER-USER is the chain Docker guarantees it will not flush.
        assert "DOCKER-USER" in script
        # Traffic to the gateway is INPUT, not FORWARD: a rule only in
        # DOCKER-USER would never see it.
        assert "INPUT" in script
        # Re-running a deploy must converge, not stack duplicates.
        assert "-C" in script, "each rule must be tested before it is inserted"
        assert "--check" in script, "an operator must be able to ask without changing anything"

    def test_it_blocks_sibling_docker_networks_not_only_the_host(self) -> None:
        """The worse of the two paths, and the one a first version missed.

        Bridge networks on one host route to each other by default, and the
        demonstrator NEEDS three routed containers. Measured 2026-08-07 from
        the egress proxy's namespace against the development stack: PostgreSQL
        answered `fe_sendauth: no password supplied`, Redis answered `NOAUTH
        Authentication required` — full protocol conversations. Binding those
        ports to 127.0.0.1 on the host protects nothing: the container address
        is reached directly.
        """
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        for private in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"):
            assert private in script, (
                f"{private} must be dropped: it covers sibling Docker networks "
                "and the local network, not only the host"
            )

    def test_the_envelope_may_still_talk_to_itself(self) -> None:
        """A blanket private-range drop would cut the envelope in half."""
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert (
            "-j RETURN" in script
        ), "the demonstrator's own subnets must be exempted BEFORE the drops"

    def test_replies_are_exempted_or_the_published_port_dies(self) -> None:
        """The reply to a request from the host matches the drop exactly."""
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "ESTABLISHED,RELATED" in script, (
            "without a conntrack exemption the edge's published port answers "
            "nothing, and the failure reads as a broken application"
        )

    def test_the_subnets_are_discovered_not_typed(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "docker network inspect" in script, (
            "Docker allocates the subnets; a hand-written range protects nothing "
            "the day the allocation moves"
        )


class TestTheHardeningRunsUnderTheDeploymentAccount:
    """It runs over ssh, as a non-root user, with a stripped PATH.

    Two assumptions the script made and the Raspberry refused on 2026-08-07:

    - ``command -v iptables`` finds nothing, because iptables lives in
      /usr/sbin and an ssh COMMAND gets a non-login shell whose PATH omits it.
      Reproduced in a Debian container: with the PATH an ssh command carries,
      the lookup fails while /usr/sbin/iptables sits right there;
    - writing netfilter rules is root's, and the deployment account is not.
    """

    def test_it_looks_where_debian_actually_puts_iptables(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "/usr/sbin/iptables" in script, (
            "an ssh command's PATH omits /usr/sbin; searching only the PATH "
            "reports 'no iptables binary' on a host that has two"
        )

    def test_it_escalates_without_a_prompt(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "sudo -n" in script, (
            "netfilter needs root, and there is no terminal on the other end "
            "of an ssh command: an interactive prompt would hang until timeout"
        )
        assert "NOPASSWD" in script, (
            "a refusal must say how to grant the right, not only that it was " "refused"
        )

    def test_an_unusable_docker_is_not_reported_as_a_missing_network(self) -> None:
        """A diagnosis that blames the wrong thing costs the next hour."""
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "docker network ls >/dev/null 2>&1" in script, (
            "a socket the user may not open produced 'no network found for "
            "compose project', which blames the demonstrator for a permission "
            "problem"
        )
        assert "usermod -aG docker" in script


class TestTheHostPathAndTheForwardPathAreNotTheSameChain:
    """The demonstrator may talk to its peers. It may not talk to the machine.

    Both statements were carried by one chain, and one chain cannot carry them:
    a bridge gateway belongs to the subnet it serves, so ``-s demo -d demo -j
    RETURN`` — the rule squid, postfix, the API and the tunnel all depend on —
    also matched ``demo -> the host``, and it came first.

    The Raspberry answered exactly that on 2026-08-07, through the probe this
    hardening exists to satisfy::

        HOST REACHABLE from inside the demonstrator:
            172.24.0.1:2222 (ssh)   172.25.0.1:2222 (ssh)   ...

    Reproduced on a real daemon, an ``internal`` network and a listener in the
    host namespace: reachable before, refused after, peers and Internet intact.
    """

    def test_the_host_path_has_its_own_chain(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "LIA-DEMO-HOSTGUARD" in script, (
            "INPUT needs rules of its own: what the demonstrator may say to "
            "this machine is not what it may say to its own containers"
        )
        assert 'INPUT 1 -j "$HOSTCHAIN"' in script

    def test_the_forward_chain_never_governs_the_host_path(self) -> None:
        """Where the permission lives is the whole of the fix."""
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert 'INPUT 1 -j "$CHAIN"' not in script, (
            "the forward chain opens by allowing the demonstrator's own "
            "subnets; on the INPUT path that permission covers the gateways, "
            "which are the host"
        )
        assert '-D INPUT -j "$CHAIN"' in script, (
            "an upgraded host keeps the previous version's jump — rebuilding "
            "chains does not remove a jump — so it must be deleted, not just "
            "outranked by the new guard"
        )

    def test_every_subnet_is_dropped_towards_the_host(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert '-A "$HOSTCHAIN" -s "$subnet" -j DROP' in script, (
            "no destination filter: the host answers on its bridge gateways, "
            "on its LAN address and on loopback, and the demonstrator needs "
            "none of them"
        )
        assert '-A "$HOSTCHAIN" -m conntrack' in script, (
            "replies to a host-initiated connection must survive, or a "
            "published port answers nothing and it looks like a broken app"
        )


class TestTheVerificationBelievesTheKernelNotItsOwnQuestion:
    """``iptables-nft -C`` denied rules that ``-S`` printed verbatim.

    Measured 2026-08-07, same shell, seconds after installing them: two of
    three ``-s <subnet> -j DROP`` rules answered *Bad rule (does a matching
    rule exist in that chain?)* while ``-S`` listed all three. A check that
    reports an installed rule missing is worse than no check — it sends the
    next person to re-run a correct install and teaches them to disbelieve the
    alarm.
    """

    def test_it_reads_what_the_kernel_prints(self) -> None:
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert 'rules_of() { $SUDO "$IPT" -S "$1"' in script
        assert '-C "$HOSTCHAIN" -s' not in script, (
            "-C is unreliable on the nft variant; the verification must read " "the printed ruleset"
        )

    def test_it_matches_the_reply_exemption_on_its_invariant_part(self) -> None:
        """``-S`` prints back ``RELATED,ESTABLISHED``, not what we wrote."""
        script = (ROOT / "scripts/deploy/harden-demo-host.sh").read_text(encoding="utf-8")

        assert "grep -- '-m conntrack' | grep -q -- '-j RETURN'" in script, (
            "matching the literal ESTABLISHED,RELATED spelling would report a "
            "present exemption as missing"
        )
