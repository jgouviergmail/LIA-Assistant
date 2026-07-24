"""A correlated FOR_EACH item belongs to exactly one parent — and must survive it.

Prod defect (2026-07-23, measured in the dev API logs): asked for the weather of
two appointments on the same day, the FOR_EACH ran two weather calls. Both tools
derived their registry id from place + day, so both emitted **the same id**::

    step_2_item_0  touched_ids: ["weather_fee011"]  total_registry_size: 4
    step_2_item_1  touched_ids: ["weather_fee011"]  total_registry_size: 4  <- unchanged

The accumulator is a plain ``dict.update()``, so the second branch overwrote the
first: only the second appointment kept its ``correlated_to``, and the first was
rendered with no weather at all despite the call having been made and paid for.

The identity of a correlated item therefore has to include its parent. These
tests pin that property, its determinism (checkpoint replay), and the fact that
UNcorrelated items keep their id untouched.
"""

from __future__ import annotations

import pytest

from src.core.field_names import FIELD_CORRELATED_TO
from src.domains.agents.data_registry.models import RegistryItemType, generate_registry_id
from src.domains.agents.orchestration.correlation_detector import detect_correlations
from src.domains.agents.orchestration.parallel_executor import _correlated_item_id

pytestmark = [pytest.mark.unit]

# The colliding id observed in production: same place, same day -> same hash.
COLLIDING_ID = generate_registry_id(RegistryItemType.WEATHER, "forecast_Paris_2026-07-25")
PARENT_A = "event_30f9a6"  # Rdv podologue, 11:15
PARENT_B = "event_541387"  # Brunch, 13:00


def _weather_item(item_id: str, parent_id: str | None, label: str) -> dict:
    """A serialized registry item shaped like the executor produces."""
    return {
        "id": item_id,
        "type": RegistryItemType.WEATHER.value,
        "payload": {"location": {"name": "Paris"}, "date": "2026-07-25", "label": label},
        "meta": {"source": "openweathermap", FIELD_CORRELATED_TO: parent_id},
    }


def _event_item(item_id: str, summary: str) -> dict:
    return {
        "id": item_id,
        "type": RegistryItemType.EVENT.value,
        "payload": {"summary": summary},
        "meta": {"source": "google_calendar", FIELD_CORRELATED_TO: None},
    }


class TestCorrelatedItemIdentity:
    def test_same_item_under_two_parents_yields_two_ids(self):
        """The exact prod collision: two appointments, one weather id."""
        a = _correlated_item_id(COLLIDING_ID, _weather_item(COLLIDING_ID, PARENT_A, "a"), PARENT_A)
        b = _correlated_item_id(COLLIDING_ID, _weather_item(COLLIDING_ID, PARENT_B, "b"), PARENT_B)
        assert a != b
        assert a != COLLIDING_ID and b != COLLIDING_ID

    def test_is_deterministic_across_replays(self):
        """Checkpoint replay / HITL resumption must recompute the same id."""
        item = _weather_item(COLLIDING_ID, PARENT_A, "a")
        assert _correlated_item_id(COLLIDING_ID, item, PARENT_A) == _correlated_item_id(
            COLLIDING_ID, item, PARENT_A
        )

    def test_keeps_the_type_prefixed_shape(self):
        """`filter_registry_by_relevant_ids` matches on the `{type}_{hash}` suffix."""
        new_id = _correlated_item_id(
            COLLIDING_ID, _weather_item(COLLIDING_ID, PARENT_A, "a"), PARENT_A
        )
        prefix, _, suffix = new_id.partition("_")
        assert prefix == RegistryItemType.WEATHER.value.lower()
        assert len(suffix) == 6 and all(c in "0123456789abcdef" for c in suffix)

    def test_unknown_type_keeps_the_original_id(self):
        """Never break the id shape to fix a collision."""
        item = {"id": "mystery_1", "type": "NOT_A_REGISTRY_TYPE", "payload": {}, "meta": {}}
        assert _correlated_item_id("mystery_1", item, PARENT_A) == "mystery_1"

    def test_self_enrichment_keeps_the_parent_id(self):
        """A FOR_EACH that re-emits its own parent is an UPDATE, not a derivation.

        `generate_registry_id(type, entity_id)` is a pure hash of the business id,
        so `update_event_tool` / `get_*_details` under
        ``for_each: $steps.step_1.events`` rebuild the parent's exact id.
        Re-identifying there would duplicate the entity and leave the stale copy
        alive next to the fresh one.
        """
        parent_event = _event_item(PARENT_A, "Rdv podologue (updated)")
        assert _correlated_item_id(PARENT_A, parent_event, PARENT_A) == PARENT_A

    def test_different_items_under_the_same_parent_stay_distinct(self):
        first = _correlated_item_id(
            "weather_aaaaaa", _weather_item("weather_aaaaaa", PARENT_A, "a"), PARENT_A
        )
        second = _correlated_item_id(
            "weather_bbbbbb", _weather_item("weather_bbbbbb", PARENT_A, "b"), PARENT_A
        )
        assert first != second


class TestRenderedOutcome:
    """What the user actually loses: one appointment silently without weather."""

    def _registry(self, *, per_parent_ids: bool) -> dict:
        """Build the registry the executor hands to the display layer.

        ``per_parent_ids=False`` reproduces the pre-fix accumulation (both
        branches writing the same key through ``dict.update``).
        """
        registry: dict = {
            PARENT_A: _event_item(PARENT_A, "Rdv podologue"),
            PARENT_B: _event_item(PARENT_B, "Brunch"),
        }
        for parent, label in ((PARENT_A, "for-A"), (PARENT_B, "for-B")):
            item = _weather_item(COLLIDING_ID, parent, label)
            key = (
                _correlated_item_id(COLLIDING_ID, item, parent) if per_parent_ids else COLLIDING_ID
            )
            item["id"] = key
            registry[key] = item  # same dict.update semantics as the accumulator
        return registry

    def test_without_per_parent_ids_one_appointment_loses_its_weather(self):
        """Characterizes the defect — kept so the fix cannot be silently undone."""
        clusters, _ = detect_correlations(self._registry(per_parent_ids=False))
        assert len(clusters) == 1
        assert clusters[0].cluster_id == PARENT_B  # the last writer wins
        # ...and PARENT_A is rendered with no weather child at all.

    def test_with_per_parent_ids_each_appointment_keeps_its_own_weather(self):
        clusters, _ = detect_correlations(self._registry(per_parent_ids=True))
        assert {c.cluster_id for c in clusters} == {PARENT_A, PARENT_B}
        by_parent = {c.cluster_id: c for c in clusters}
        assert len(by_parent[PARENT_A].child_items) == 1
        assert len(by_parent[PARENT_B].child_items) == 1
        # Each parent gets ITS OWN payload, not the other's.
        assert by_parent[PARENT_A].child_items[0][1]["label"] == "for-A"
        assert by_parent[PARENT_B].child_items[0][1]["label"] == "for-B"

    def test_an_updated_parent_replaces_itself_instead_of_duplicating(self):
        """The self-enrichment guard, observed at the registry level."""
        registry: dict = {PARENT_A: _event_item(PARENT_A, "Rdv podologue")}
        refreshed = _event_item(PARENT_A, "Rdv podologue (moved to 12:00)")
        key = _correlated_item_id(PARENT_A, refreshed, PARENT_A)
        refreshed["id"] = key
        registry[key] = refreshed
        assert list(registry) == [PARENT_A], "the update must not create a second entity"
        assert registry[PARENT_A]["payload"]["summary"].endswith("(moved to 12:00)")
