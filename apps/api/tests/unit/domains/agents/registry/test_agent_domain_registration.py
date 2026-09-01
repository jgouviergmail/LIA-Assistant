"""Every registered agent's domain must be a domain the system knows.

There was already a guard for this, and it could not see the problem. It walks
the registry OUTWARD — for each declared domain, its declared agent names —
so an agent whose domain was never declared is invisible to it by construction.
That is a false negative in the guard's shape, not an oversight in its use, and
it is why two agents shipped for months emitting a warning at every catalogue
rebuild.

This one walks the other way: from the manifests INWARD. An agent whose domain
is neither in ``DOMAIN_REGISTRY``, nor a dynamic MCP domain, nor a declared
platform capability fails the build.

Deliberately a CI guard and not a boot-time assert, though the repository's own
doctrine suggests one for registries: here an assert would crash production the
day someone adds an agent named off-convention. The build failing is the same
protection without the outage.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry import agent_manifest_definitions as defs
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.domain_exemptions import is_platform_domain
from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY, is_mcp_domain

pytestmark = pytest.mark.unit


def _declared_manifests() -> list[object]:
    """Every AgentManifest defined in the definitions module."""
    from src.domains.agents.registry.catalogue import AgentManifest

    return [
        value
        for name, value in vars(defs).items()
        if isinstance(value, AgentManifest) and not name.startswith("_")
    ]


def _extract(agent_name: str) -> str:
    return AgentRegistry._extract_domain_from_agent_name(  # type: ignore[misc]
        AgentRegistry.__new__(AgentRegistry), agent_name
    )


class TestEveryAgentHasAKnownDomain:
    def test_there_are_manifests_to_check(self) -> None:
        """Guards the guard: an import rename would make the rest vacuous."""
        assert len(_declared_manifests()) >= 10

    def test_every_agent_resolves_to_a_domain_the_system_knows(self) -> None:
        unknown: list[str] = []
        for manifest in _declared_manifests():
            name = manifest.name  # type: ignore[attr-defined]
            domain = _extract(name)
            if domain in DOMAIN_REGISTRY or is_mcp_domain(domain) or is_platform_domain(domain):
                continue
            unknown.append(f"{name} -> {domain}")

        assert not unknown, (
            "These agents resolve to a domain nothing declares, so a "
            "domain-filtered catalogue would silently omit them: "
            f"{unknown}. Register the domain, rename the agent onto an "
            "existing one, or declare it a platform capability."
        )

    def test_the_diagnostics_agent_sits_under_devops(self) -> None:
        """Its own manifest points at devops_agent as the acting counterpart,
        and the devops domain description already covers deployment
        diagnostics and production error analysis word for word."""
        assert _extract(defs.DIAGNOSTICS_AGENT_MANIFEST.name) == "devops"

    def test_the_python_sandbox_is_a_platform_capability_not_a_data_domain(self) -> None:
        """A DomainConfig REQUIRES a result_key, and this agent produces no
        domain payload — it returns a computation. Forcing it in would invent
        a `$steps.step_N.pythons` reference nothing can ever produce."""
        assert is_platform_domain(_extract(defs.PYTHON_SANDBOX_AGENT_MANIFEST.name))


class TestPlatformExemptionIsNarrow:
    def test_it_never_swallows_a_real_data_domain(self) -> None:
        for domain in ("email", "contact", "event", "task", "devops"):
            assert not is_platform_domain(domain), (
                f"'{domain}' is a data domain; exempting it would hide exactly "
                "the mistake this guard exists to catch."
            )

    def test_an_unknown_name_is_not_exempt_by_accident(self) -> None:
        assert not is_platform_domain("whatever")
        assert not is_platform_domain("")
