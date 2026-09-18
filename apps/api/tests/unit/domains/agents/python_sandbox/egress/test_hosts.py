"""Host validation and the four statuses a declared host can have (ADR-298)."""

from __future__ import annotations

import pytest

from src.domains.agents.python_sandbox.egress.hosts import (
    ConnectorHost,
    HostStatus,
    InvalidHost,
    classify_hosts,
    normalize_hosts,
)

pytestmark = pytest.mark.unit

BRAVE = ConnectorHost(
    host="api.search.brave.com",
    connector="brave_search",
    auth_method="header",
    auth_name="X-Subscription-Token",
    auth_prefix="",
)


class TestNormalizeHosts:
    def test_lowercases_strips_and_deduplicates(self) -> None:
        assert normalize_hosts(
            ["API.Search.Brave.com", " api.search.brave.com. ", "Example.ORG"], cap=5
        ) == (
            "api.search.brave.com",
            "example.org",
        )

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "https://example.org",
            "example.org:443",
            "example.org/path",
            "1.1.1.1",
            "[::1]",
            "localhost",
            "-bad.example.org",
            "münchen.example",
            "a" * 64 + ".example.org",
            "under_score.example.org",
        ],
    )
    def test_refuses_what_the_proxy_cannot_match_exactly(self, raw: str) -> None:
        with pytest.raises(InvalidHost):
            normalize_hosts([raw], cap=5)

    def test_non_ascii_names_are_refused_with_the_punycode_hint(self) -> None:
        with pytest.raises(InvalidHost, match="punycode"):
            normalize_hosts(["münchen.example"], cap=5)

    def test_the_cap_is_enforced_after_deduplication(self) -> None:
        assert normalize_hosts(["a.org", "a.org", "b.org"], cap=2) == ("a.org", "b.org")
        with pytest.raises(InvalidHost, match="at most 2"):
            normalize_hosts(["a.org", "b.org", "c.org"], cap=2)


class TestClassifyHosts:
    def test_each_status_and_its_data_scope(self) -> None:
        decision = classify_hosts(
            ("api.search.brave.com", "api.example.org", "granted.example", "mystery.example"),
            connectors={"api.search.brave.com": BRAVE},
            operator_hosts={"api.example.org"},
            grants={"granted.example": True},
        )
        assert decision.statuses == {
            "api.search.brave.com": HostStatus.CONNECTOR,
            "api.example.org": HostStatus.OPERATOR,
            "granted.example": HostStatus.GRANT,
            "mystery.example": HostStatus.UNKNOWN,
        }
        assert decision.unknown == ("mystery.example",)
        assert decision.credentials == (BRAVE,)
        assert decision.share_turn_data is True

    def test_a_grant_without_data_narrows_the_whole_run(self) -> None:
        """The minimum rule: one host approved WITHOUT the data makes the run
        run without — otherwise adding a permissive host would lift a
        restriction the person placed on another."""
        decision = classify_hosts(
            ("api.search.brave.com", "granted.example"),
            connectors={"api.search.brave.com": BRAVE},
            operator_hosts=set(),
            grants={"granted.example": False},
        )
        assert decision.share_turn_data is False
        assert decision.unknown == ()

    def test_a_connector_host_wins_over_a_grant_on_the_same_name(self) -> None:
        """The connector brings a credential; a grant never does."""
        decision = classify_hosts(
            ("api.search.brave.com",),
            connectors={"api.search.brave.com": BRAVE},
            operator_hosts=set(),
            grants={"api.search.brave.com": False},
        )
        assert decision.statuses["api.search.brave.com"] is HostStatus.CONNECTOR
        assert decision.share_turn_data is True

    def test_no_host_means_no_network_and_nothing_to_ask(self) -> None:
        decision = classify_hosts((), connectors={}, operator_hosts=set(), grants={})
        assert decision.statuses == {}
        assert decision.unknown == ()
        assert decision.credentials == ()
