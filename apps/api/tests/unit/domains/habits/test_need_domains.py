"""What each registered domain allows a recurring need to become (ADR-375).

Declared, never inferred: a domain added to the registry without a decision
here refuses to boot, and every connector category named must exist.
"""

from __future__ import annotations

import pytest

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES
from src.domains.habits.need_domains import (
    NEED_DOMAINS,
    assert_need_domains_complete,
    automatable_domains,
    connector_category_of,
)

pytestmark = pytest.mark.unit


def test_every_registered_domain_carries_a_decision() -> None:
    assert set(NEED_DOMAINS) == set(DOMAIN_REGISTRY)


def test_the_boot_guard_accepts_the_registry() -> None:
    assert_need_domains_complete(DOMAIN_REGISTRY)


def test_the_boot_guard_refuses_an_undecided_domain() -> None:
    with pytest.raises(AssertionError, match="new_domain"):
        assert_need_domains_complete([*DOMAIN_REGISTRY, "new_domain"])


def test_the_boot_guard_refuses_a_retired_domain_still_declared() -> None:
    with pytest.raises(AssertionError, match="event"):
        assert_need_domains_complete([name for name in DOMAIN_REGISTRY if name != "event"])


def test_every_named_connector_category_exists() -> None:
    named = {d.connector_category for d in NEED_DOMAINS.values() if d.connector_category}
    assert named <= set(CONNECTOR_FUNCTIONAL_CATEGORIES)


def test_the_automatable_domains_are_the_state_reads() -> None:
    assert automatable_domains() == frozenset(
        {"event", "email", "task", "weather", "health", "sms"}
    )


def test_a_connector_category_is_read_by_domain() -> None:
    assert connector_category_of("event") == "calendar"
    assert connector_category_of("email") == "email"
    assert connector_category_of("weather") is None  # keyless instance default (ADR-307)
    assert connector_category_of("unregistered") is None
