"""Every registry type declares the plural key its payload is filed under.

ADR-085 doctrine, applied to the one registry table that had no guard.
Measured 2026-09-10: 25 ``RegistryItemType`` members, 24 entries. The missing
one was ``BROWSER_PAGE``, and the silent fallback below it
(``item.type.value.lower() + "s"``) produced ``browser_pages`` where both
declared authorities — ``DOMAIN_REGISTRY`` and ``TYPE_TO_DOMAIN_MAP`` — say
``browsers``. A key nobody reads is a step output nobody sees.
"""

import pytest

from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.agents.tools.output import (
    REGISTRY_TYPE_TO_KEY,
    assert_registry_key_completeness,
)
from src.domains.agents.utils.type_domain_mapping import TYPE_TO_DOMAIN_MAP


def test_every_registry_type_declares_its_plural_key() -> None:
    missing = sorted(t.value for t in RegistryItemType if t not in REGISTRY_TYPE_TO_KEY)
    assert missing == [], f"no plural key declared for {missing}"


def test_the_completeness_assert_passes_on_the_shipped_table() -> None:
    assert_registry_key_completeness()


def test_the_completeness_assert_names_what_is_missing() -> None:
    """A guard that says nothing is a guard nobody can act on."""
    absent = next(iter(REGISTRY_TYPE_TO_KEY))
    trimmed = {k: v for k, v in REGISTRY_TYPE_TO_KEY.items() if k is not absent}
    with pytest.raises(AssertionError, match=absent.value):
        assert_registry_key_completeness(trimmed)


def test_no_type_is_filed_under_a_key_the_taxonomy_contradicts() -> None:
    """Two tables, one fact: the plural key of a domain type.

    ``TYPE_TO_DOMAIN_MAP`` declares the planner-visible result key; this table
    files the payload under it. Where both name a type they must agree, or a
    plan referencing ``$steps.step_N.<key>`` resolves to nothing.
    """
    disagreements = {
        item_type.value: (REGISTRY_TYPE_TO_KEY[item_type], TYPE_TO_DOMAIN_MAP[item_type.value][1])
        for item_type in RegistryItemType
        if item_type.value in TYPE_TO_DOMAIN_MAP
        and item_type in REGISTRY_TYPE_TO_KEY
        and REGISTRY_TYPE_TO_KEY[item_type] != TYPE_TO_DOMAIN_MAP[item_type.value][1]
    }
    assert disagreements == {}, f"filed under a key the taxonomy contradicts: {disagreements}"
