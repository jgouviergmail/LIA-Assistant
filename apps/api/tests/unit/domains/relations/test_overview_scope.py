"""The 360° scope — a selection the tool applies, not a hint it may honour.

The request leaves the browser as a chat ``?intent=``, which carries prose and
nothing else. This model is what makes the reader's choice a guarantee, so its
edges matter more than its happy path:

- **an empty selection means NONE, never "everything"**. Silence must not be
  generous here: a scope that grew when the reader cleared it would spend the
  provider quota they had just asked to save;
- **the bounds are enforced AND published** (ADR-184) — whatever the validator
  can reject, its producer must be able to read;
- **an unreadable stored shape degrades to the defaults**, because the column
  is JSONB and may have been written by an older version. A half-shape reaching
  the tool would silently drop sections nobody deselected.
"""

from __future__ import annotations

import pytest

from src.core.constants import (
    RELATION_OVERVIEW_MAX_ITEMS_CEILING,
    RELATION_OVERVIEW_MAX_ITEMS_DEFAULT,
)
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewRole,
    OverviewSection,
    RelationOverviewScope,
)

pytestmark = pytest.mark.unit


class TestDefaults:
    def test_a_first_time_reader_gets_everything(self) -> None:
        scope = RelationOverviewScope.default()
        assert set(scope.sections) == set(OverviewSection)
        assert set(scope.directions) == set(OverviewDirection)
        assert set(scope.roles) == set(OverviewRole)
        assert scope.max_items == RELATION_OVERVIEW_MAX_ITEMS_DEFAULT

    def test_every_section_of_the_page_is_selectable(self) -> None:
        """The selector offers sources, so a source with no enum value could
        never be deselected — and would silently always be read."""
        assert {section.value for section in OverviewSection} == {
            "open_loops",
            "calls",
            "memories",
            "peer_messages",
            "contact",
            "emails",
            "events",
        }


class TestAnEmptySelectionMeansNone:
    def test_no_section_selected_includes_nothing(self) -> None:
        scope = RelationOverviewScope(sections=[])
        assert all(not scope.includes(section) for section in OverviewSection)

    def test_deselecting_one_leaves_the_others(self) -> None:
        scope = RelationOverviewScope(sections=[OverviewSection.EMAILS, OverviewSection.CONTACT])
        assert scope.includes(OverviewSection.EMAILS)
        assert not scope.includes(OverviewSection.CALLS)

    def test_no_direction_selected_is_not_both_directions(self) -> None:
        assert RelationOverviewScope(directions=[]).directions == []


class TestBoundsArePublished:
    def test_the_ceiling_is_enforced(self) -> None:
        with pytest.raises(ValueError):
            RelationOverviewScope(max_items=RELATION_OVERVIEW_MAX_ITEMS_CEILING + 1)

    def test_zero_is_refused(self) -> None:
        """A cleared form field must never reach here as 0 — it would make the
        whole write fail and lose every box the reader had ticked."""
        with pytest.raises(ValueError):
            RelationOverviewScope(max_items=0)

    def test_the_bounds_are_readable_on_the_schema(self) -> None:
        """ADR-184: a limit the system enforces must be published to whoever
        produces the value — here, the form that pre-fills it."""
        field = RelationOverviewScope.model_json_schema()["properties"]["max_items"]
        assert field["minimum"] == 1
        assert field["maximum"] == RELATION_OVERVIEW_MAX_ITEMS_CEILING

    def test_an_unknown_section_is_refused_rather_than_ignored(self) -> None:
        with pytest.raises(ValueError):
            RelationOverviewScope(sections=["astrology"])


class TestFromStored:
    def test_a_round_trip_survives_the_jsonb_column(self) -> None:
        scope = RelationOverviewScope(
            sections=[OverviewSection.CONTACT],
            directions=[OverviewDirection.SENT],
            roles=[OverviewRole.ORGANIZER],
            max_items=3,
        )
        assert RelationOverviewScope.from_stored(scope.model_dump(mode="json")) == scope

    def test_never_saved_reads_as_the_defaults(self) -> None:
        assert RelationOverviewScope.from_stored(None) == RelationOverviewScope.default()

    def test_a_shape_this_version_cannot_read_degrades_to_the_defaults(self) -> None:
        """Not an error the reader can act on: "everything" is the answer they
        had before the setting existed."""
        for stored in ({"sections": "everything"}, {"max_items": 999}, "nonsense", 42, []):
            assert RelationOverviewScope.from_stored(stored) == RelationOverviewScope.default()

    def test_a_partial_shape_fills_the_missing_halves_with_the_defaults(self) -> None:
        """A payload written before `roles` existed must not lose the roles."""
        scope = RelationOverviewScope.from_stored({"sections": ["emails"], "max_items": 4})
        assert scope.sections == [OverviewSection.EMAILS]
        assert set(scope.roles) == set(OverviewRole)
        assert scope.max_items == 4

    def test_an_empty_stored_selection_stays_empty(self) -> None:
        """The one case where degrading would be WRONG: an empty list is a
        deliberate choice, not a missing value."""
        scope = RelationOverviewScope.from_stored({"sections": []})
        assert scope.sections == []
