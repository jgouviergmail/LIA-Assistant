"""Unit tests for data_registry.state (merge_registry LRU eviction).

Regression coverage for the 2026-07 codebase audit (wave 1):
- The LRU eviction sort must handle a registry holding MIXED item forms
  (Pydantic ``RegistryItem`` objects with ``datetime`` timestamps alongside
  serialized dicts with ISO-string timestamps). The sort key used to return
  ``datetime`` or ``str`` depending on the form, so ``sorted()`` raised
  ``TypeError`` as soon as the registry exceeded ``registry_max_items``
  with both forms present.
"""

from datetime import UTC, datetime

import pytest

from src.core.config import get_settings
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.data_registry.state import merge_registry

# ============================================================================
# HELPERS
# ============================================================================


def _make_item(idx: int, *, as_dict: bool) -> RegistryItem | dict:
    """Build a registry item with a deterministic timestamp.

    Higher ``idx`` means more recent. ``as_dict=True`` returns the serialized
    form produced by ``model_dump(mode="json")`` (ISO-string timestamp), as
    stored by ``_execute_tool``.
    """
    item = RegistryItem(
        id=f"contact_{idx}",
        type=RegistryItemType.CONTACT,
        payload={"displayName": f"Person {idx}"},
        meta=RegistryItemMeta(
            source="google_contacts",
            domain="contacts",
            timestamp=datetime(2026, 1, 1, idx, 0, 0, tzinfo=UTC),
        ),
    )
    return item.model_dump(mode="json") if as_dict else item


# ============================================================================
# REGRESSION: eviction sort with mixed item forms (audit item 3)
# ============================================================================


@pytest.mark.unit
def test_merge_registry_eviction_with_mixed_forms(monkeypatch):
    """Eviction beyond the cap must not raise with mixed object/dict forms.

    Keeps the most recent items regardless of whether their timestamp is a
    ``datetime`` (RegistryItem) or an ISO string (serialized dict).
    """
    monkeypatch.setattr(get_settings(), "registry_max_items", 3)

    # Mixed forms on both sides of the merge: even idx = objects, odd = dicts
    current = {f"contact_{i}": _make_item(i, as_dict=(i % 2 == 1)) for i in range(3)}
    updates = {f"contact_{i}": _make_item(i, as_dict=(i % 2 == 1)) for i in range(3, 5)}

    merged = merge_registry(current, updates)

    # The 3 most recent items survive (idx 2, 3, 4), oldest are evicted
    assert set(merged.keys()) == {"contact_2", "contact_3", "contact_4"}


@pytest.mark.unit
def test_merge_registry_eviction_unreadable_meta_sorts_as_oldest(monkeypatch):
    """Items with unreadable meta fall back to epoch and are evicted first."""
    monkeypatch.setattr(get_settings(), "registry_max_items", 2)

    current = {
        "contact_1": _make_item(1, as_dict=False),
        "broken_item": {"payload": {"x": 1}},  # no meta at all
    }
    updates = {"contact_2": _make_item(2, as_dict=True)}

    merged = merge_registry(current, updates)

    assert set(merged.keys()) == {"contact_1", "contact_2"}


@pytest.mark.unit
def test_merge_registry_no_eviction_below_cap(monkeypatch):
    """Below the cap, merge is a plain last-write-wins union (no sort involved)."""
    monkeypatch.setattr(get_settings(), "registry_max_items", 10)

    current = {"contact_1": _make_item(1, as_dict=False)}
    updates = {"contact_2": _make_item(2, as_dict=True)}

    merged = merge_registry(current, updates)

    assert set(merged.keys()) == {"contact_1", "contact_2"}
