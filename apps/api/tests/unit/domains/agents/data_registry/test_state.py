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
from src.domains.agents.data_registry.state import _get_item_timestamp, merge_registry

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


# ============================================================================
# CORE REDUCER CONTRACT: last-write-wins + None handling
# ============================================================================


def _named_item(item_id: str, name: str, hour: int) -> RegistryItem:
    """A RegistryItem with a distinguishable payload and deterministic timestamp."""
    return RegistryItem(
        id=item_id,
        type=RegistryItemType.CONTACT,
        payload={"displayName": name},
        meta=RegistryItemMeta(
            source="google_contacts",
            timestamp=datetime(2026, 1, 1, hour, 0, 0, tzinfo=UTC),
        ),
    )


@pytest.mark.unit
class TestMergeRegistryContract:
    """The documented reducer contract, exercised on the WIRED merge_registry."""

    def test_same_id_in_updates_overwrites_current(self, monkeypatch):
        """Last-write-wins: an update to an existing ID replaces the payload.

        This is the core reducer semantic ("new items with existing IDs
        overwrite previous items") and the below-cap test does not exercise it
        (it uses distinct IDs). A regression here silently serves stale entity
        data to reference resolution across turns.
        """
        monkeypatch.setattr(get_settings(), "registry_max_items", 10)

        current = {"contact_1": _named_item("contact_1", "Old Name", hour=1)}
        updates = {"contact_1": _named_item("contact_1", "New Name", hour=2)}

        merged = merge_registry(current, updates)

        assert len(merged) == 1
        assert merged["contact_1"].payload["displayName"] == "New Name"

    def test_none_current_is_treated_as_empty(self, monkeypatch):
        """First call (no prior state): current=None must not raise."""
        monkeypatch.setattr(get_settings(), "registry_max_items", 10)

        merged = merge_registry(None, {"contact_1": _named_item("contact_1", "A", hour=1)})

        assert set(merged.keys()) == {"contact_1"}

    def test_none_updates_returns_current_unchanged(self):
        """A node that writes nothing to the channel (updates=None) is a no-op.

        Returned verbatim WITHOUT touching settings — proven by not patching the
        cap: if the code read settings on this path it would use the real value,
        but more importantly the identical object must come back.
        """
        current = {"contact_1": _named_item("contact_1", "A", hour=1)}

        assert merge_registry(current, None) is current

    def test_both_none_returns_empty_dict(self):
        assert merge_registry(None, None) == {}

    def test_eviction_keeps_strictly_newest(self, monkeypatch):
        """Ordering correctness: with a cap of 2 over 4 distinct-timestamp items,
        exactly the two most recent survive (independent of insertion order)."""
        monkeypatch.setattr(get_settings(), "registry_max_items", 2)

        current = {
            "c_old": _named_item("c_old", "Old", hour=1),
            "c_mid": _named_item("c_mid", "Mid", hour=2),
        }
        updates = {
            "c_new": _named_item("c_new", "New", hour=5),
            "c_recent": _named_item("c_recent", "Recent", hour=4),
        }

        merged = merge_registry(current, updates)

        assert set(merged.keys()) == {"c_new", "c_recent"}


# ============================================================================
# _get_item_timestamp — normalization feeding the eviction sort
# ============================================================================


@pytest.mark.unit
class TestGetItemTimestamp:
    """All forms must normalize to an aware UTC datetime so ``sorted()`` never
    mixes aware/naive/str (which would raise TypeError mid-eviction)."""

    def test_aware_datetime_on_registry_item(self):
        ts = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
        item = RegistryItem(
            id="x",
            type=RegistryItemType.CONTACT,
            payload={},
            meta=RegistryItemMeta(source="s", timestamp=ts),
        )
        assert _get_item_timestamp(item) == ts

    def test_naive_datetime_is_coerced_to_utc(self):
        item = RegistryItem(
            id="x",
            type=RegistryItemType.CONTACT,
            payload={},
            meta=RegistryItemMeta(source="s", timestamp=datetime(2026, 3, 1, 12, 0, 0)),
        )
        result = _get_item_timestamp(item)
        assert result.tzinfo is UTC
        assert result == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    def test_iso_string_with_z_suffix(self):
        item = {"meta": {"timestamp": "2026-03-01T12:00:00Z"}}
        assert _get_item_timestamp(item) == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    def test_iso_string_with_offset(self):
        item = {"meta": {"timestamp": "2026-03-01T13:00:00+01:00"}}
        assert _get_item_timestamp(item) == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    def test_naive_iso_string_is_coerced_to_utc(self):
        item = {"meta": {"timestamp": "2026-03-01T12:00:00"}}
        result = _get_item_timestamp(item)
        assert result.tzinfo is UTC
        assert result == datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)

    def test_invalid_string_falls_back_to_epoch(self):
        item = {"meta": {"timestamp": "not-a-date"}}
        assert _get_item_timestamp(item) == datetime(1970, 1, 1, tzinfo=UTC)

    def test_missing_meta_falls_back_to_epoch(self):
        assert _get_item_timestamp({"payload": {}}) == datetime(1970, 1, 1, tzinfo=UTC)

    def test_dict_meta_without_timestamp_falls_back_to_epoch(self):
        item = {"meta": {"source": "gmail"}}
        assert _get_item_timestamp(item) == datetime(1970, 1, 1, tzinfo=UTC)
