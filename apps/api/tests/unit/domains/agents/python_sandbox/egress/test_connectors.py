"""The connector hosts a run may carry a credential for are DERIVED from the
client classes — never from a hand-typed table (ADR-298)."""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from src.domains.agents.python_sandbox.egress.connectors import (
    API_KEY_CLIENTS,
    active_connector_hosts,
    derive_connector_hosts,
    real_keys_for,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


class FakeGate:
    """The tool's connector service: which connectors are active, which keys exist."""

    def __init__(self, active: set[ConnectorType], keys: dict[ConnectorType, str]) -> None:
        self.active = active
        self.keys = keys

    async def is_connector_active(self, user_id: uuid.UUID, connector_type: ConnectorType) -> bool:
        return connector_type in self.active

    async def get_api_key_credentials(
        self, user_id: uuid.UUID, connector_type: ConnectorType
    ) -> APIKeyCredentials | None:
        key = self.keys.get(connector_type)
        return APIKeyCredentials(api_key=key) if key else None


def _api_key_client_classes_in_source() -> set[str]:
    """Every ``class X(BaseAPIKeyClient)`` under connectors/clients, by AST."""
    root = Path(__file__).parents[6] / "src" / "domains" / "connectors" / "clients"
    found: set[str] = set()
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id == "BaseAPIKeyClient" for base in node.bases
            ):
                found.add(node.name)
    return found


class TestTheListIsComplete:
    def test_every_api_key_client_class_is_declared(self) -> None:
        declared = {cls.__name__ for cls in API_KEY_CLIENTS}
        assert declared == _api_key_client_classes_in_source(), (
            "an API-key client class exists that the egress derivation does not "
            "read — its host would be `unknown` and the person asked for what "
            "their own connector already permits"
        )


class TestTheDerivation:
    def test_reads_host_and_auth_shape_from_each_class(self) -> None:
        hosts = derive_connector_hosts()
        brave = hosts["api.search.brave.com"]
        assert (brave.connector, brave.auth_method, brave.auth_name, brave.auth_prefix) == (
            "brave_search",
            "header",
            "X-Subscription-Token",
            "",
        )
        pplx = hosts["api.perplexity.ai"]
        assert (pplx.auth_method, pplx.auth_name, pplx.auth_prefix) == (
            "header",
            "Authorization",
            "Bearer",
        )
        owm = hosts["api.openweathermap.org"]
        assert (owm.auth_method, owm.auth_name, owm.auth_prefix) == ("query", "appid", "")

    def test_hosts_are_bare_lowercase_names(self) -> None:
        for host in derive_connector_hosts():
            assert host == host.lower() and "/" not in host and ":" not in host


class TestTheAccount:
    async def test_only_active_connectors_bring_a_host(self) -> None:
        gate = FakeGate(active={ConnectorType.BRAVE_SEARCH}, keys={})
        assert set(await active_connector_hosts(gate, USER)) == {"api.search.brave.com"}

    async def test_keys_are_read_for_the_declared_connector_hosts_only(self) -> None:
        hosts = derive_connector_hosts()
        gate = FakeGate(
            active={ConnectorType.BRAVE_SEARCH, ConnectorType.PERPLEXITY},
            keys={ConnectorType.BRAVE_SEARCH: "BSA-real", ConnectorType.PERPLEXITY: "pplx-real"},
        )
        keys = await real_keys_for(gate, USER, (hosts["api.search.brave.com"],))
        assert keys == {"brave_search": "BSA-real"}

    async def test_a_connector_deactivated_meanwhile_brings_no_key(self) -> None:
        hosts = derive_connector_hosts()
        gate = FakeGate(active=set(), keys={})
        assert await real_keys_for(gate, USER, (hosts["api.search.brave.com"],)) == {}
