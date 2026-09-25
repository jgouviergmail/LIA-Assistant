"""The router's menu of domains must match what the deployment can actually run.

Some domains are deployment-flag-gated. For each, the flag already gates the
tools and the REST surface, so a domain left in the menu while its flag is off
is a domain the router can pick and the planner can then plan over nothing —
which never raises, it just answers badly.

``peer`` was in exactly that state until 2026-07-30: ``peers_enabled`` gated
the router, the catalogue manifests and the tool modules, but not this
chokepoint. ``ticket`` was in it until 2026-09-24: it DECLARED
``workboard_enabled`` in the taxonomy while this table did not hold it, because
the check below read the table against the taxonomy and never the reverse.
"""

from contextlib import ExitStack
from unittest.mock import patch

import pytest

from src.domains.agents.services.analysis.domain_availability import (
    FLAG_GATED_DOMAINS,
    build_available_domains,
)

# The mapping is imported, not restated: a domain added to the table without a
# real flag — or with the wrong one — must fail here, which a local copy of the
# table could never catch.
EXPECTED_GATED = {
    "telephony": "telephony_enabled",
    "document": "rag_spaces_enabled",
    "peer": "peers_enabled",
    "ticket": "workboard_enabled",
    "journal": "journals_enabled",
}


def test_gated_table_matches_the_documented_deployment_flags():
    assert FLAG_GATED_DOMAINS == EXPECTED_GATED


def _names(**flags: bool) -> set[str]:
    """Available domain names with every deployment flag of the table forced."""
    with ExitStack() as stack:
        for flag in FLAG_GATED_DOMAINS.values():
            stack.enter_context(patch(f"src.core.config.settings.{flag}", flags[flag]))
        stack.enter_context(
            patch("src.infrastructure.mcp.registration.get_admin_mcp_domains", return_value={})
        )
        return {d["name"] for d in build_available_domains()}


ALL_OFF = dict.fromkeys(FLAG_GATED_DOMAINS.values(), False)
ALL_ON = dict.fromkeys(FLAG_GATED_DOMAINS.values(), True)


@pytest.mark.parametrize(("domain", "flag"), sorted(FLAG_GATED_DOMAINS.items()))
def test_domain_is_withdrawn_when_its_flag_is_off(domain, flag):
    assert domain not in _names(**{**ALL_ON, flag: False})


@pytest.mark.parametrize(("domain", "flag"), sorted(FLAG_GATED_DOMAINS.items()))
def test_domain_is_offered_when_its_flag_is_on(domain, flag):
    assert domain in _names(**{**ALL_OFF, flag: True})


def test_a_flag_only_withdraws_its_own_domain():
    """No collateral: turning one feature off must not hide the others."""
    for domain, flag in FLAG_GATED_DOMAINS.items():
        offered = _names(**{**ALL_ON, flag: False})
        assert offered >= set(FLAG_GATED_DOMAINS) - {domain}


def test_unrelated_domains_survive_every_flag_combination():
    """The core domains are never deployment-gated."""
    core = {"event", "contact", "email", "task", "weather"}
    assert core <= _names(**ALL_OFF)
    assert core <= _names(**ALL_ON)


def test_every_flag_gated_domain_declares_its_flag_in_the_taxonomy():
    """The registry metadata and this chokepoint must name the same flag.

    Without this, a domain can declare a feature flag nobody enforces — which
    is precisely how `peer` stayed routable on instances that had it disabled.
    """
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    for domain, flag in FLAG_GATED_DOMAINS.items():
        config = DOMAIN_REGISTRY.get(domain)
        assert config is not None, f"{domain} is gated here but absent from the taxonomy"
        declared = (config.metadata or {}).get("feature_flag")
        if declared is not None:
            assert declared == flag


def test_every_flag_the_taxonomy_declares_is_enforced_here():
    """The reverse direction: a declared flag this chokepoint ignores is decoration."""
    from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY

    declared = {
        name: config.metadata["feature_flag"]
        for name, config in DOMAIN_REGISTRY.items()
        if (config.metadata or {}).get("feature_flag") and config.is_routable
    }
    assert declared.items() <= FLAG_GATED_DOMAINS.items()
