"""The hosts a turn may reach without asking — one derivation (ADR-298)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.python_sandbox.egress.hosts import ConnectorHost
from src.domains.agents.python_sandbox.egress.offer import merge_reachable, offer_for_account

pytestmark = pytest.mark.unit


def _brave() -> ConnectorHost:
    return ConnectorHost(
        host="api.search.brave.com",
        connector="brave_search",
        auth_method="header",
        auth_name="X-Subscription-Token",
        auth_prefix="",
    )


class TestMergeReachable:
    def test_connectors_first_then_the_operator_sorted_and_folded(self) -> None:
        hosts = merge_reachable(
            {"api.search.brave.com": _brave()}, ["Status.Example.org", "api.example.org"]
        )
        assert [h.host for h in hosts] == [
            "api.search.brave.com",
            "api.example.org",
            "status.example.org",
        ]
        assert hosts[0].credential is not None and hosts[0].token_env == "LIA_KEY_BRAVE_SEARCH"
        assert hosts[1].credential is None and hosts[1].token_env is None

    def test_a_connector_host_on_the_operator_list_keeps_its_credential(self) -> None:
        hosts = merge_reachable({"api.search.brave.com": _brave()}, ["API.SEARCH.BRAVE.COM"])
        assert len(hosts) == 1 and hosts[0].credential is not None

    def test_nothing_reachable_is_an_empty_tuple(self) -> None:
        assert merge_reachable({}, []) == ()


class TestOfferForAccount:
    async def test_a_blind_connector_read_keeps_the_operator_hosts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "python_sandbox_egress_hosts", ["status.example.org"])
        monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", False)

        async def _boom(user_id: Any, connector_type: Any) -> bool:
            raise RuntimeError("db down")

        offer = await offer_for_account(uuid.uuid4(), SimpleNamespace(is_connector_active=_boom))
        assert [h.host for h in offer.hosts] == ["status.example.org"]
        assert offer.ask_enabled is False

    async def test_no_gate_means_the_operator_hosts_alone(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "python_sandbox_egress_hosts", ["a.example"])
        offer = await offer_for_account(uuid.uuid4(), None)
        assert [h.host for h in offer.hosts] == ["a.example"]
